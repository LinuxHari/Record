from typing import TypedDict

from record.workers import celery_worker_app


class EmbedPayload(TypedDict):
    key: str
    user_id: str

@celery_worker_app.task(name="records.tasks.assets.embed")
async def embed_asset():
    pass