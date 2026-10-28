from record.app.auth.jwt_service import JwtService
from record.db.cache.redis.service import RedisService
from record.dependencies import get_settings


class TokenBlacklistService:
    BLACKLIST_KEY_PREFIX = "blacklist:sid:"

    def __init__(self, redis: RedisService):
        settings = get_settings()
        self.redis = redis
        self.access_ttl_seconds = (
            settings.jwt_access_expiry_minutes * 60 + JwtService.LEEWAY_SECONDS
        )

    async def revoke_session(self, session_id: str) -> None:
        await self.redis.set_value(
            f"{self.BLACKLIST_KEY_PREFIX}{session_id}",
            "1",
            ttl_seconds=self.access_ttl_seconds,
        )

    async def revoke_sessions(self, session_ids: list[str]) -> None:
        if not session_ids:
            return
        await self.redis.set_values_with_ttl(
            [
                (
                    f"{self.BLACKLIST_KEY_PREFIX}{session_id}",
                    "1",
                    self.access_ttl_seconds,
                )
                for session_id in session_ids
            ]
        )

    async def is_revoked(self, session_id: str) -> bool:
        return await self.redis.key_exists(f"{self.BLACKLIST_KEY_PREFIX}{session_id}")
