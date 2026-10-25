from functools import lru_cache
from datetime import datetime, timezone

from record.config import Settings


@lru_cache()
def get_settings():
    return Settings()

def utc_now() -> datetime:
    return datetime.now(timezone.utc)
