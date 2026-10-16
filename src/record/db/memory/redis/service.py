import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import NoScriptError, RedisError
from typing import Sequence

from record.exceptions.http_excpetions import ServiceUnavailableException


class RedisService:
    TIMEOUT = 5.0
    SOCKET_TIMEOUT = 5.0

    def __init__(self, *, name: str, url: str, max_connections: int) -> None:
        self.name: str = name
        self.url: str = url
        self.max_connections: int = max_connections
        self._pool: aioredis.BlockingConnectionPool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return

        self._pool = aioredis.BlockingConnectionPool.from_url(
            self.url,
            max_connections=self.max_connections,
            timeout=self.TIMEOUT,
            socket_timeout=self.SOCKET_TIMEOUT,
            retry=Retry(ExponentialBackoff(), retries=3),
            decode_responses=True,
        )

    def _get_client(self) -> aioredis.Redis:
        if self._pool is None:
            raise ServiceUnavailableException()
        return aioredis.Redis(connection_pool=self._pool)

    async def get_value(self, key: str) -> str | None:
        try:
            async with self._get_client() as client:
                return await client.get(key)
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def set_value(self, key: str, value: str, *, ttl_seconds: int) -> None:
        try:
            async with self._get_client() as client:
                await client.set(key, value, ex=ttl_seconds)
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def set_values_with_ttl(
        self, entries: Sequence[tuple[str, str, int]]
    ) -> None:
        if not entries:
            return
        try:
            async with self._get_client() as client:
                async with client.pipeline(transaction=True) as pipeline:
                    for key, value, ttl_seconds in entries:
                        pipeline.set(key, value, ex=ttl_seconds)
                    await pipeline.execute()
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def delete_keys(self, *keys: str) -> int:
        if not keys:
            return 0
        try:
            async with self._get_client() as client:
                return int(await client.delete(*keys))
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def key_exists(self, key: str) -> bool:
        try:
            async with self._get_client() as client:
                return bool(await client.exists(key))
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def set_remove(self, key: str, *members: str) -> int:
        if not members:
            return 0
        try:
            async with self._get_client() as client:
                return int(await client.srem(key, *members))
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def set_members(self, key: str) -> set[str]:
        try:
            async with self._get_client() as client:
                return set(await client.smembers(key))
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def load_script(self, script: str) -> str:
        try:
            async with self._get_client() as client:
                return str(await client.script_load(script))
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def store_session(
        self,
        *,
        refresh_key: str,
        refresh_value: str,
        session_key: str,
        session_value: str,
        user_sessions_key: str,
        session_id: str,
        ttl_seconds: int,
    ) -> None:
        try:
            async with self._get_client() as client:
                async with client.pipeline(transaction=True) as pipeline:
                    pipeline.set(refresh_key, refresh_value, ex=ttl_seconds)
                    pipeline.set(session_key, session_value, ex=ttl_seconds)
                    pipeline.sadd(user_sessions_key, session_id)
                    pipeline.expire(user_sessions_key, ttl_seconds, nx=True)
                    pipeline.expire(user_sessions_key, ttl_seconds, gt=True)
                    await pipeline.execute()
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def eval_sha(self, sha: str, key: str) -> list[str]:
        try:
            async with self._get_client() as client:
                return await client.evalsha(sha, 1, key)
        except NoScriptError:
            raise
        except RedisError as exc:
            raise ServiceUnavailableException() from exc

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None