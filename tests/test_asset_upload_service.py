import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from record.app.user.models import User
from record.app.assets.config import PDF_CONTENT_TYPE
from record.app.assets.models import AssetStatus
from record.app.assets.service import AssetService
from record.exceptions.http_excpetions import BadRequestException


USER_ID = "c6f02f7e-60c3-4f4f-9f88-77a5898a7a5a"
CHUNK_SIZE = AssetService.MULTIPART_CHUNK_SIZE_IN_MB * 1024 * 1024


def create_asset_service() -> tuple[AssetService, MagicMock, MagicMock, MagicMock, MagicMock]:
    asset_repository = MagicMock()
    asset_upload_repository = MagicMock()
    s3_service = MagicMock()
    queue_service = MagicMock()

    return (
        AssetService(
            asset_repository=asset_repository,
            asset_upload_repository=asset_upload_repository,
            s3_service=s3_service,
            queue_service=queue_service,
        ),
        asset_repository,
        asset_upload_repository,
        s3_service,
        queue_service,
    )


def test_initiate_asset_upload_creates_multipart_upload_and_persists_metadata() -> None:
    service, _, asset_upload_repository, s3_service, _ = create_asset_service()
    s3_service.create_multipart_upload = AsyncMock(
        return_value=("upload-123", "assets/file.pdf")
    )
    expected_urls = [{"part_number": 1, "url": "https://s3.test/part/1"}]
    s3_service.generate_presigned_part_urls = AsyncMock(return_value=expected_urls)
    asset_upload_repository.create = AsyncMock()

    urls = asyncio.run(
        service.initiate_asset_upload(
            {
                "name": "Annual Report.pdf",
                "type": PDF_CONTENT_TYPE,
                "size": 1,
            },
            USER_ID,
        )
    )

    assert urls == expected_urls
    s3_service.create_multipart_upload.assert_awaited_once()
    file_name = s3_service.create_multipart_upload.await_args.kwargs["file_name"]
    assert file_name.endswith("-annual_report.pdf")
    s3_service.create_multipart_upload.assert_awaited_once_with(
        file_name=file_name,
        content_type=PDF_CONTENT_TYPE,
    )
    s3_service.generate_presigned_part_urls.assert_awaited_once_with(
        file_name=file_name,
        upload_id="upload-123",
        total_parts=1,
    )
    saved_upload = asset_upload_repository.create.await_args.args[0]
    assert saved_upload.upload_id == "upload-123"
    assert saved_upload.user_id == USER_ID
    assert saved_upload.key == "assets/file.pdf"


def test_initiate_asset_upload_rejects_file_size_out_of_range() -> None:
    service, _, asset_upload_repository, s3_service, _ = create_asset_service()
    s3_service.create_multipart_upload = AsyncMock()
    asset_upload_repository.create = AsyncMock()

    with pytest.raises(BadRequestException):
        asyncio.run(
            service.initiate_asset_upload(
                {"name": "report.pdf", "type": PDF_CONTENT_TYPE, "size": 0},
                USER_ID,
            )
        )

    s3_service.create_multipart_upload.assert_not_awaited()
    asset_upload_repository.create.assert_not_awaited()


def test_complete_asset_upload_validates_parts_creates_asset_and_enqueues_embedding() -> None:
    service, asset_repository, asset_upload_repository, s3_service, queue_service = (
        create_asset_service()
    )
    upload_id = "upload-123"
    upload = SimpleNamespace(
        user_id=UUID(USER_ID),
        upload_id=upload_id,
        key="assets/file.pdf",
        name="Annual Report.pdf",
        type=PDF_CONTENT_TYPE,
        size=CHUNK_SIZE + 1,
    )
    parts = [
        {"PartNumber": 1, "ETag": "etag-1"},
        {"PartNumber": 2, "ETag": "etag-2"},
    ]
    asset_upload_repository.find_by_id = AsyncMock(return_value=upload)
    s3_service.list_parts = AsyncMock(
        return_value=[
            {"PartNumber": 1, "ETag": "etag-1", "Size": CHUNK_SIZE},
            {"PartNumber": 2, "ETag": "etag-2", "Size": 1},
        ]
    )
    s3_service.complete_multipart_upload = AsyncMock()
    created_asset = SimpleNamespace(id="asset-123")
    asset_repository.create = AsyncMock(return_value=created_asset)
    asset_upload_repository.delete_by_id = AsyncMock()

    asyncio.run(
        service.asset_upload_complete(
            user_id=USER_ID,
            upload_id=upload_id,
            parts=parts,
        )
    )

    s3_service.complete_multipart_upload.assert_awaited_once_with(
        key=upload.key,
        upload_id=upload_id,
        parts=parts,
    )
    new_asset = asset_repository.create.await_args.kwargs["data"]
    assert new_asset.user_id == USER_ID
    assert new_asset.name == upload.name
    assert new_asset.type == upload.type
    assert new_asset.size == upload.size
    assert new_asset.key == upload.key
    assert new_asset.status is AssetStatus.PENDING
    queue_service.send_task.assert_called_once_with(
        "records.tasks.assets.embed",
        kwargs={
            "payload": {
                "key": upload.key,
                "user_id": USER_ID,
                "asset_id": str(created_asset.id),
            }
        },
    )
    asset_upload_repository.delete_by_id.assert_awaited_once_with(
        user_id=USER_ID,
        upload_id=upload_id,
    )


def test_complete_asset_upload_rejects_mismatched_etag_without_completing_upload() -> None:
    service, asset_repository, asset_upload_repository, s3_service, queue_service = (
        create_asset_service()
    )
    upload = SimpleNamespace(
        key="assets/file.pdf",
        name="Annual Report.pdf",
        type=PDF_CONTENT_TYPE,
        size=1,
    )
    asset_upload_repository.find_by_id = AsyncMock(return_value=upload)
    s3_service.list_parts = AsyncMock(
        return_value=[{"PartNumber": 1, "ETag": "actual-etag", "Size": 1}]
    )
    s3_service.complete_multipart_upload = AsyncMock()
    asset_repository.create = AsyncMock()
    asset_upload_repository.delete_by_id = AsyncMock()

    with pytest.raises(BadRequestException, match="ETag does not match"):
        asyncio.run(
            service.asset_upload_complete(
                user_id=USER_ID,
                upload_id="upload-123",
                parts=[{"PartNumber": 1, "ETag": "submitted-etag"}],
            )
        )

    s3_service.complete_multipart_upload.assert_not_awaited()
    asset_repository.create.assert_not_awaited()
    queue_service.send_task.assert_not_called()
    asset_upload_repository.delete_by_id.assert_not_awaited()
