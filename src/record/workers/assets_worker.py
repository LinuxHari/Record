from record.workers import celery_worker_app

@celery_worker_app.task(name="records.tasks.assets.embed")
async def embed_asset():
    pass