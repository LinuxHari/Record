from celery import Celery
from kombu import Queue

from record.dependencies import get_settings

class CeleryConfig:
    task_queues = [
        Queue('default_assets_queue', durable=True),
        Queue('email_queue', durable=True),
    ]
    task_create_missing_queues = False
    task_default_queue = 'default_assets_queue'

    task_serializer = 'json'
    result_serializer = 'json'
    accept_content = ['json']

    # Rate Limiting
    # task_annotations = {
    #     'record.tasks.send_email': {'rate_limit': '10/m'}  # Max 10 per minute
    # }

celery_app = Celery(
    "assets",
    broker=get_settings().celery_queue_url,
)

celery_app.config_from_object(CeleryConfig)
