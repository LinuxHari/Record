import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from record.app.ai.embedding.hash_service import HashService
from record.app.ai.embedding.service import EmbeddingService
from record.app.assets.models import AssetStatus
from record.workers import assets_worker


def test_hash_service_returns_sha256_digest() -> None:
    assert HashService().hash("hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def create_embedding_service() -> tuple[
    EmbeddingService, MagicMock, MagicMock, MagicMock, MagicMock
]:
    chunk_service = MagicMock()
    s3_service = MagicMock()
    hash_service = MagicMock()
    embedding_repository = MagicMock()
    asset_repository = MagicMock()
    service = EmbeddingService(
        chunk_service=chunk_service,
        s3_service=s3_service,
        hash_service=hash_service,
        embedding_repository=embedding_repository,
        asset_repository=asset_repository,
    )
    return service, s3_service, hash_service, embedding_repository, asset_repository


def test_embed_asset_stores_each_chunk_and_marks_asset_success() -> None:
    service, s3_service, hash_service, embedding_repository, asset_repository = (
        create_embedding_service()
    )
    s3_service.generate_presigned_get_url = AsyncMock(return_value="https://s3.test/doc")
    chunk = SimpleNamespace(
        text="content",
        meta=SimpleNamespace(headings=["Heading"]),
        doc_items=[SimpleNamespace(self_ref="#/1")],
    )

    async def parse_content(*, source: str):
        assert source == "https://s3.test/doc"
        yield chunk

    service.chunk_service.parse_content = parse_content
    service.embed = AsyncMock(return_value=[0.1, 0.2])
    hash_service.hash = MagicMock(side_effect=["content-hash", "section-hash"])
    embedding_repository.create = AsyncMock()
    asset_repository.update_by_id = AsyncMock()

    asyncio.run(
        service.embed_asset(
            s3_key="assets/doc.pdf",
            user_id="user-123",
            asset_id="asset-123",
        )
    )

    saved_embedding = embedding_repository.create.await_args.kwargs["data"]
    assert saved_embedding.user_id == "user-123"
    assert saved_embedding.asset_id == "asset-123"
    assert saved_embedding.text_context == "content"
    assert saved_embedding.context_hash == "content-hash"
    assert saved_embedding.section == "Heading"
    assert saved_embedding.section_hash == "section-hash"
    assert saved_embedding.location == "#/1"
    assert saved_embedding.embeddings == [0.1, 0.2]
    asset_repository.update_by_id.assert_awaited_once_with(
        user_id="user-123",
        asset_id="asset-123",
        update_data={"status": AssetStatus.SUCCESS},
    )


def test_embed_asset_marks_asset_failed_when_processing_raises() -> None:
    service, s3_service, _, embedding_repository, asset_repository = (
        create_embedding_service()
    )
    s3_service.generate_presigned_get_url = AsyncMock(
        side_effect=RuntimeError("S3 unavailable")
    )
    embedding_repository.create = AsyncMock()
    asset_repository.update_by_id = AsyncMock()

    asyncio.run(
        service.embed_asset(
            s3_key="assets/doc.pdf",
            user_id="user-123",
            asset_id="asset-123",
        )
    )

    embedding_repository.create.assert_not_awaited()
    asset_repository.update_by_id.assert_awaited_once_with(
        user_id="user-123",
        asset_id="asset-123",
        update_data={"status": AssetStatus.FAILED},
    )


def test_worker_opens_db_context_and_invokes_embedding_service(monkeypatch) -> None:
    runner = asyncio.Runner()
    monkeypatch.setattr(assets_worker, "_runner", runner)
    monkeypatch.setattr(assets_worker, "_runner_pid", os.getpid())

    service = MagicMock()
    service.embed_asset = AsyncMock()
    monkeypatch.setattr(assets_worker, "_embed_asset_service_factory", lambda: service)
    session_entered = False

    class SessionContext:
        async def __aenter__(self):
            nonlocal session_entered
            session_entered = True

        async def __aexit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(
        assets_worker.pg_sessionmanager,
        "session",
        lambda: SessionContext(),
    )
    payload = {
        "key": "assets/doc.pdf",
        "user_id": "user-123",
        "asset_id": "asset-123",
    }

    try:
        assets_worker.embed_asset.run(payload)
    finally:
        runner.close()

    assert session_entered
    service.embed_asset.assert_awaited_once_with(
        s3_key="assets/doc.pdf",
        user_id="user-123",
        asset_id="asset-123",
    )
