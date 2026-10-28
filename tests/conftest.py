import os


_TEST_SETTINGS = {
    "DB_URL": "postgresql+asyncpg://user:password@localhost:5432/record",
    "APP_URL": "http://localhost:8000",
    "REDIS_CACHE_URL": "redis://localhost:6379/10",
    "CELERY_QUEUE_URL": "amqp://guest:guest@localhost:5672//",
    "AWS_SECRET_ACCESS_KEY": "test-secret",
    "AWS_ACCESS_KEY_ID": "test-access",
    "AWS_REGION_NAME": "us-east-1",
    "AWS_S3_BUCKET_NAME": "test-bucket",
    "JWT_SECRET": "test-jwt-secret-that-is-long-enough-for-testing",
    "JWT_ISSUER": "http://localhost:8000",
    "JWT_AUDIENCE": "http://localhost:8000",
    "JWT_ACCESS_EXPIRY_MINUTES": "15",
    "REFRESH_EXPIRY_DAYS": "7",
    "DOCLING_SERVER_URL": "http://localhost:5001",
    "EMBEDDING_MODEL": "test-model",
}

for _name, _value in _TEST_SETTINGS.items():
    os.environ.setdefault(_name, _value)
