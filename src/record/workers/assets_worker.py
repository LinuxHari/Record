from celery import Celery

celery_app = Celery(
    "assets",
    broker="",
    backend="rpc://",
)