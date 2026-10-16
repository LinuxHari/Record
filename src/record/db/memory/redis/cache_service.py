from record.db.memory.redis.service import RedisService
from record.dependencies import get_settings

cache_service = RedisService(name="cache_service", url=get_settings().redis_cache_url, max_connections=30)

def get_cache_service():
    return cache_service