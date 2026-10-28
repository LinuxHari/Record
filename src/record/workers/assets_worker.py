import asyncio
import os
from typing import TypedDict

from celery.signals import worker_process_shutdown

from record.app.shared.dependencies import get_embed_service
from record.db.sql.postgres.session import pg_sessionmanager
from record.workers import celery_worker_app


class EmbedPayload(TypedDict):
    key: str
    user_id: str
    asset_id: str


_runner: asyncio.Runner | None = None
_runner_pid: int | None = None


async def _embed_asset(payload: EmbedPayload) -> None:
    async with pg_sessionmanager.session():
        service = get_embed_service()
        await service.embed_asset(
            s3_key=payload["key"],
            user_id=payload["user_id"],
            asset_id=payload["asset_id"],
        )


@celery_worker_app.task(name="records.tasks.assets.embed")
def embed_asset(payload: EmbedPayload) -> None:
    global _runner, _runner_pid

    process_id = os.getpid()
    if _runner is None or _runner_pid != process_id:
        _runner = asyncio.Runner()
        _runner_pid = process_id

    _runner.run(_embed_asset(payload))


@worker_process_shutdown.connect
def close_worker_resources(**_: object) -> None:
    if _runner is None or _runner_pid != os.getpid():
        return

    _runner.run(pg_sessionmanager.close())
    _runner.close()