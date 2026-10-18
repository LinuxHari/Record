from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio.client import Pipeline
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    NoScriptError,
    ReadOnlyError,
    RedisError,
    TimeoutError as RedisTimeoutError,
)

from record.exceptions.http_excpetions import ServiceUnavailableException

logger = logging.getLogger(__name__)

_UNAVAILABLE_ERRORS = (RedisConnectionError, RedisTimeoutError, ReadOnlyError)


class RedisService:
    def __init__(
        self,
        *,
        name: str,
        url: str,
        max_connections: int,
        pool_timeout: float = 2.0,
        socket_timeout: float = 2.0,
        socket_connect_timeout: float = 2.0,
        health_check_interval: int = 30,
        retries: int = 2,
    ) -> None:
        self.name = name
        self.url = url
        self.max_connections = max_connections
        self.pool_timeout = pool_timeout
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.health_check_interval = health_check_interval
        self.retries = retries

        self._pool: aioredis.BlockingConnectionPool | None = None
        self._client: aioredis.Redis | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Create the pool and verify Redis is reachable (fail fast)."""
        async with self._connect_lock:
            if self._client is not None:
                return

            pool = aioredis.BlockingConnectionPool.from_url(
                self.url,
                max_connections=self.max_connections,
                timeout=self.pool_timeout,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                socket_keepalive=True,
                health_check_interval=self.health_check_interval,
                retry=Retry(ExponentialBackoff(cap=0.5, base=0.05), self.retries),
                decode_responses=True,
            )
            client = aioredis.Redis(connection_pool=pool)
            try:
                await client.ping()
            except RedisError:
                await client.aclose()
                await pool.aclose()
                logger.exception(
                    "Redis initial connection failed",
                    extra={"redis_service": self.name},
                )
                raise

            self._pool = pool
            self._client = client
            logger.info(
                "Redis connected",
                extra={"redis_service": self.name},
            )

    async def disconnect(self) -> None:
        async with self._connect_lock:
            client, pool = self._client, self._pool
            self._client = None
            self._pool = None
            if client is not None:
                await client.aclose()
            if pool is not None:
                await pool.aclose()

    async def ping(self) -> bool:
        """Health-check helper (e.g. for a /health endpoint)."""
        async with self._guard("ping") as client:
            return bool(await client.ping())

    @asynccontextmanager
    async def _guard(self, operation: str) -> AsyncGenerator[aioredis.Redis]:
        client = self._client
        if client is None:
            logger.error(
                "Redis operation attempted before connection",
                extra={"redis_service": self.name, "operation": operation},
            )
            raise ServiceUnavailableException()
        try:
            yield client
        except _UNAVAILABLE_ERRORS as exc:
            logger.error(
                "Redis unavailable during operation",
                extra={
                    "redis_service": self.name,
                    "operation": operation,
                    "exception_type": type(exc).__name__,
                },
            )
            raise ServiceUnavailableException() from exc
        except NoScriptError:
            raise  # caller handles it (reload script + retry)
        except RedisError:
            logger.exception(
                "Redis operation failed",
                extra={"redis_service": self.name, "operation": operation},
            )
            raise

    @staticmethod
    def _require_positive_ttl(ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer")

    async def get_value(self, key: str) -> str | None:
        async with self._guard("get") as client:
            return await client.get(key)

    async def set_value(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self._require_positive_ttl(ttl_seconds)
        async with self._guard("set") as client:
            await client.set(key, value, ex=ttl_seconds)

    async def set_values_with_ttl(
        self, entries: Sequence[tuple[str, str, int]]
    ) -> None:
        if not entries:
            return
        for _, _, ttl_seconds in entries:
            self._require_positive_ttl(ttl_seconds)
        async with self._guard("set_many") as client:
            async with client.pipeline(transaction=True) as pipe:
                for key, value, ttl_seconds in entries:
                    pipe.set(key, value, ex=ttl_seconds)
                await pipe.execute()

    async def delete_keys(self, *keys: str) -> int:
        if not keys:
            return 0
        async with self._guard("delete") as client:
            return int(await client.delete(*keys))

    async def key_exists(self, key: str) -> bool:
        async with self._guard("exists") as client:
            return bool(await client.exists(key))

    async def load_script(self, script: str) -> str:
        async with self._guard("script_load") as client:
            return str(await client.script_load(script))

    async def eval_sha(self, sha: str, *keys: str, args: Sequence[Any] = ()) -> Any:
        """Run a loaded script by SHA.

        Raises NoScriptError if Redis no longer has the script (restart,
        failover, SCRIPT FLUSH); the caller reloads it and retries.
        """
        async with self._guard("evalsha") as client:
            return await client.evalsha(sha, len(keys), *keys, *args)

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
        self._require_positive_ttl(ttl_seconds)
        now = time.time()
        async with self._guard("store_session") as client:
            async with client.pipeline(transaction=True) as pipe:
                pipe.set(refresh_key, refresh_value, ex=ttl_seconds)
                pipe.set(session_key, session_value, ex=ttl_seconds)
                pipe.zadd(user_sessions_key, {session_id: now + ttl_seconds})
                pipe.zremrangebyscore(user_sessions_key, "-inf", now)
                pipe.expire(user_sessions_key, ttl_seconds, nx=True)
                pipe.expire(user_sessions_key, ttl_seconds, gt=True)
                await pipe.execute()

    async def list_session_ids(self, user_sessions_key: str) -> list[str]:
        """Return only the user's non-expired session ids."""
        now = time.time()
        async with self._guard("list_sessions") as client:
            async with client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(user_sessions_key, "-inf", now)
                pipe.zrangebyscore(user_sessions_key, now, "+inf")
                results = await self._execute(pipe)
        return list(results[1])

    async def delete_session(
        self,
        *,
        session_key: str,
        refresh_key: str,
        user_sessions_key: str,
        session_id: str,
    ) -> None:
        """Atomically remove a session, its refresh token and its index entry."""
        async with self._guard("delete_session") as client:
            async with client.pipeline(transaction=True) as pipe:
                pipe.delete(session_key, refresh_key)
                pipe.zrem(user_sessions_key, session_id)
                await pipe.execute()

    async def delete_all_sessions(
        self,
        *,
        user_sessions_key: str,
        session_key_for: str,
        refresh_key_for: str,
    ) -> int:
        """Log a user out everywhere.

        `session_key_for` / `refresh_key_for` are format strings with a
        `{session_id}` placeholder, e.g. "session:{session_id}".
        """
        session_ids = await self.list_session_ids(user_sessions_key)
        if not session_ids:
            return 0
        keys = [
            fmt.format(session_id=sid)
            for sid in session_ids
            for fmt in (session_key_for, refresh_key_for)
        ]
        async with self._guard("delete_all_sessions") as client:
            async with client.pipeline(transaction=True) as pipe:
                pipe.delete(*keys)
                pipe.delete(user_sessions_key)
                await pipe.execute()
        return len(session_ids)

    @staticmethod
    async def _execute(pipe: Pipeline) -> list[Any]:
        return await pipe.execute()