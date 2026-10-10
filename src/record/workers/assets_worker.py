from celery import Celery
from record.dependencies import get_settings

celery_app = Celery(
    "assets",
    broker=get_settings().queue_url,
    backend="rpc://",
)