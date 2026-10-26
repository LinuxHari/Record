import math
import uuid

from typing import TypedDict

from record.aws.s3_service import AwsS3, MultipartPart
from record.exceptions.http_excpetions import BadRequestException
from record.app.assets.repository import AssetRepository, AssetUploadRepository
from record.app.assets.models import Asset, AssetUpload
from record.app.assets.config import MAX_ASSET_SIZE_BYTES


class AssetMetadata(TypedDict):
    name: str
    size: int
    type: str


class AssetService:
    MULTIPART_CHUNK_SIZE_IN_MB = 64
    MAX_MULTIPART_PARTS = math.ceil(
        MAX_ASSET_SIZE_BYTES / (MULTIPART_CHUNK_SIZE_IN_MB * 1000 * 1000)
    )

    def __init__(
        self,
        *,
        asset_repository: AssetRepository,
        asset_upload_repository: AssetUploadRepository,
        s3_service: AwsS3,
    ) -> None:
        self.s3_service: AwsS3 = s3_service
        self.asset_repository: AssetRepository = asset_repository
        self.asset_upload_repository: AssetUploadRepository = asset_upload_repository

    async def initiate_asset_upload(
        self, asset_metadata: AssetMetadata, user_id: str
    ) -> list[dict[str, int | str]]:
        file_size = asset_metadata["size"]

        if not 1 <= file_size <= MAX_ASSET_SIZE_BYTES:
            raise BadRequestException(
                f"File size must be between 1 byte and {MAX_ASSET_SIZE_BYTES / (1000 * 1000)} MB"
            )

        chunk_size_bytes = self.MULTIPART_CHUNK_SIZE_IN_MB * 1000 * 1000
        total_chunks = math.ceil(file_size / chunk_size_bytes)

        if total_chunks > self.MAX_MULTIPART_PARTS:
            raise BadRequestException(
                f"Asset upload cannot exceed {self.MAX_MULTIPART_PARTS} parts"
            )

        unique_file_name = (
            f"{uuid.uuid4()}-{asset_metadata['name'].replace(' ', '_').lower()}"
        )
        upload_id, key = await self.s3_service.create_multipart_upload(
            file_name=unique_file_name, content_type=asset_metadata["type"]
        )
        urls = await self.s3_service.generate_presigned_part_urls(
            file_name=unique_file_name,
            upload_id=upload_id,
            total_parts=total_chunks,
        )

        await self.asset_upload_repository.create(
            AssetUpload(
                upload_id=upload_id,
                name=asset_metadata["name"],
                size=asset_metadata["size"],
                type=asset_metadata["type"],
                user_id=user_id,
                key=key,
            )
        )

        return urls

    async def list_assets(self, *, user_id: str) -> list[Asset]:
        return await self.asset_repository.find_many_by_user(user_id=user_id)

    async def asset_upload_complete(
        self, *, user_id: str, upload_id: str, parts: list[MultipartPart]
    ) -> None:
        upload = await self.asset_upload_repository.find_by_id(
            user_id=user_id, upload_id=upload_id
        )

        if not upload:
            raise BadRequestException("No asset found")

        if not 1 <= upload.size <= MAX_ASSET_SIZE_BYTES:
            raise BadRequestException("Asset upload has an invalid file size")

        chunk_size_bytes = self.MULTIPART_CHUNK_SIZE_IN_MB * 1000 * 1000
        expected_parts = math.ceil(upload.size / chunk_size_bytes)

        if not 1 <= len(parts) <= self.MAX_MULTIPART_PARTS:
            raise BadRequestException(
                f"Asset upload must contain between 1 and {self.MAX_MULTIPART_PARTS} parts"
            )

        if sorted(part["PartNumber"] for part in parts) != list(
            range(1, expected_parts + 1)
        ):
            raise BadRequestException(
                f"Asset upload must contain each part number from 1 to {expected_parts}"
            )

        uploaded_parts = await self.s3_service.list_parts(
            key=upload.key, upload_id=upload_id
        )
        uploaded_parts_by_number = {part["PartNumber"]: part for part in uploaded_parts}

        if set(uploaded_parts_by_number) != set(range(1, expected_parts + 1)):
            raise BadRequestException("Uploaded parts do not match the requested parts")

        submitted_etags = {part["PartNumber"]: part["ETag"] for part in parts}

        for part_number, uploaded_part in uploaded_parts_by_number.items():
            if uploaded_part["ETag"] != submitted_etags[part_number]:
                raise BadRequestException(f"ETag does not match for part {part_number}")
            expected_size = min(
                chunk_size_bytes,
                upload.size - (part_number - 1) * chunk_size_bytes,
            )

            if uploaded_part["Size"] != expected_size:
                raise BadRequestException(
                    f"Uploaded part {part_number} has an invalid size"
                )

        await self.s3_service.complete_multipart_upload(
            key=upload.key, upload_id=upload_id, parts=parts
        )
        await self.asset_repository.create(
            data=Asset(
                user_id=user_id,
                name=upload.name,
                size=upload.size,
                type=upload.type,
                key=upload.key,
            )
        )
        await self.asset_upload_repository.delete_by_id(
            user_id=user_id, upload_id=upload_id
        )

    # def update_asset(self, asset_id, updated_data):
    #     """
    #     Updates an existing asset in the system.

    #     :param asset_id: The ID of the asset to be updated.
    #     :param updated_data: The new data for the asset.
    #     :return: A response indicating the success or failure of the update.
    #     """
    #     # Implement the logic for updating an asset
    #     pass
