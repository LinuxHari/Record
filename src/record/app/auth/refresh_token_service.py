import asyncio
import hashlib
import json
import secrets
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from redis.exceptions import NoScriptError

from record.db.cache.redis.service import RedisService
from record.dependencies import get_settings, utc_now
from record.exceptions.custom_exceptions import (
    TokenInvalidException,
    TokenReuseDetectedException,
)


@dataclass(frozen=True)
class _RefreshRecord:
    user_id: str
    session_id: str
    issued_at: int
    expires_at: int
    session_started_at: int
    used: bool


@dataclass(frozen=True)
class IssuedToken:
    token: str
    session_id: str
    expires_at: datetime


@dataclass(frozen=True)
class RotationResult:
    user_id: str
    session_id: str
    session_started_at: int


class RefreshTokenService:
    REFRESH_KEY_PREFIX = "refresh:"
    SESSION_KEY_PREFIX = "session:"
    USER_SESSIONS_KEY_PREFIX = "user_sessions:"

    ROTATE_SCRIPT = """
local v = redis.call('GET', KEYS[1])
if not v then return {'NOT_FOUND'} end
local d = cjson.decode(v)
if d.used then return {'REUSED', v} end
d.used = true
redis.call('SET', KEYS[1], cjson.encode(d), 'KEEPTTL')
return {'OK', v}
"""

    def __init__(self, redis: RedisService):
        self.redis = redis
        settings = get_settings()
        self.expiry_seconds: int = settings.refresh_expiry_days * 24 * 60 * 60
        self.max_session_seconds: int = settings.refresh_max_session_days * 24 * 60 * 60
        self._rotate_sha: str | None = None
        self._script_lock = asyncio.Lock()

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode_record(value: str) -> _RefreshRecord:
        return _RefreshRecord(**json.loads(value))

    async def _get_rotate_sha(self) -> str:
        if self._rotate_sha is not None:
            return self._rotate_sha
        async with self._script_lock:
            if self._rotate_sha is None:
                self._rotate_sha = await self.redis.load_script(self.ROTATE_SCRIPT)
        return self._rotate_sha

    async def _execute_rotate_script(self, key: str) -> list[str]:
        sha = await self._get_rotate_sha()
        try:
            return await self.redis.eval_sha(sha, key)
        except NoScriptError:
            # Redis restarted / SCRIPT FLUSH: reload and retry once.
            async with self._script_lock:
                self._rotate_sha = await self.redis.load_script(self.ROTATE_SCRIPT)
                sha = self._rotate_sha
            return await self.redis.eval_sha(sha, key)

    async def issue(
        self,
        user_id: str,
        session_id: str | None = None,
        session_started_at: int | None = None,
    ) -> IssuedToken:
        token = secrets.token_urlsafe(32)
        resolved_session_id = session_id or str(uuid.uuid4())
        now_ts = int(utc_now.timestamp())
        started_at = session_started_at or now_ts

        expires_ts = min(
            now_ts + self.expiry_seconds, started_at + self.max_session_seconds
        )
        ttl_seconds = max(1, expires_ts - now_ts)
        token_hash = self._hash(token)

        record = _RefreshRecord(
            user_id=user_id,
            session_id=resolved_session_id,
            issued_at=now_ts,
            expires_at=expires_ts,
            session_started_at=started_at,
            used=False,
        )

        await self.redis.store_session(
            refresh_key=f"{self.REFRESH_KEY_PREFIX}{token_hash}",
            refresh_value=json.dumps(asdict(record), separators=(",", ":")),
            session_key=f"{self.SESSION_KEY_PREFIX}{resolved_session_id}",
            session_value=token_hash,
            user_sessions_key=f"{self.USER_SESSIONS_KEY_PREFIX}{user_id}",
            session_id=resolved_session_id,
            ttl_seconds=ttl_seconds,
        )

        return IssuedToken(
            token=token,
            session_id=resolved_session_id,
            expires_at=datetime.fromtimestamp(expires_ts, tz=timezone.utc),
        )

    async def rotate(self, token: str) -> RotationResult:
        key = f"{self.REFRESH_KEY_PREFIX}{self._hash(token)}"
        outcome, *rest = await self._execute_rotate_script(key)

        if outcome == "NOT_FOUND":
            raise TokenInvalidException()

        record = self._decode_record(rest[0])
        if outcome == "REUSED":
            raise TokenReuseDetectedException(record.session_id, record.user_id)

        now_ts = int(uct_now.timestamp())
        if record.expires_at <= now_ts:
            raise TokenInvalidException()

        if now_ts - record.session_started_at > self.max_session_seconds:
            raise TokenInvalidException()

        return RotationResult(
            user_id=record.user_id,
            session_id=record.session_id,
            session_started_at=record.session_started_at,
        )

    async def revoke_session(self, session_id: str, user_id: str | None = None) -> None:
        session_key = f"{self.SESSION_KEY_PREFIX}{session_id}"
        current_hash = await self.redis.get_value(session_key)

        if current_hash is not None:
            refresh_key = f"{self.REFRESH_KEY_PREFIX}{current_hash}"
            if user_id is None:
                current_value = await self.redis.get_value(refresh_key)
                if current_value is not None:
                    user_id = self._decode_record(current_value).user_id
            await self.redis.delete_keys(refresh_key, session_key)
        else:
            await self.redis.delete_keys(session_key)

        if user_id is not None:
            await self.redis.set_remove(
                f"{self.USER_SESSIONS_KEY_PREFIX}{user_id}", session_id
            )

    async def revoke_by_token(self, token: str) -> str | None:
        value = await self.redis.get_value(
            f"{self.REFRESH_KEY_PREFIX}{self._hash(token)}"
        )
        if value is None:
            return None

        record = self._decode_record(value)
        await self.revoke_session(record.session_id, record.user_id)
        return record.session_id

    async def revoke_all(self, user_id: str) -> list[str]:
        sessions_key = f"{self.USER_SESSIONS_KEY_PREFIX}{user_id}"
        session_ids = sorted(await self.redis.set_members(sessions_key))

        for session_id in session_ids:
            await self.revoke_session(session_id, user_id)

        await self.redis.delete_keys(sessions_key)
        return session_ids
