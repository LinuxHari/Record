import asyncio
import hashlib
import json
import re
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Sequence

import pytest
from fastapi import Request

from redis.exceptions import NoScriptError, RedisError

from record.app.auth.jwt_service import JwtService
from record.app.auth.password_service import PasswordService
from record.app.auth.refresh_token_service import RefreshTokenService
from record.app.auth.service import AuthService
from record.app.auth.token_blacklist_service import TokenBlacklistService
from record.app.shared.dependencies import (
    get_current_user,
    get_optional_current_user,
)
from record.app.user.models import User
from record.app.user.repository import UserRepository
from record.db.cache.redis.service import RedisService
from record.exceptions.custom_exceptions import (
    TokenInvalidException,
    TokenReuseDetectedException,
)
from record.handlers.exception_handler import redis_exception_handler


class MemoryRedis(RedisService):
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.expirations: dict[str, float] = {}

    def _expire_if_needed(self, key: str) -> None:
        expiry = self.expirations.get(key)
        if expiry is not None and expiry <= time.time():
            self.values.pop(key, None)
            self.sets.pop(key, None)
            self.expirations.pop(key, None)

    async def get_value(self, key: str) -> str | None:
        self._expire_if_needed(key)
        return self.values.get(key)

    async def set_value(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self.values[key] = value
        self.sets.pop(key, None)
        self.expirations[key] = time.time() + ttl_seconds

    async def delete_keys(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(key in self.values or key in self.sets)
            self.values.pop(key, None)
            self.sets.pop(key, None)
            self.expirations.pop(key, None)
        return removed

    async def key_exists(self, key: str) -> bool:
        self._expire_if_needed(key)
        return key in self.values or key in self.sets

    async def set_remove(self, key: str, *members: str) -> int:
        members_set = self.sets.get(key, set())
        before = len(members_set)
        members_set.difference_update(members)
        return before - len(members_set)

    async def set_members(self, key: str) -> set[str]:
        self._expire_if_needed(key)
        return set(self.sets.get(key, set()))

    async def load_script(self, _script: str) -> str:
        _ = _script
        return "rotate-script"

    async def eval_sha(self, _sha: str, key: str) -> object:
        _ = _sha
        value = await self.get_value(key)
        if value is None:
            return ["NOT_FOUND"]
        data = json.loads(value)
        if data["used"]:
            return ["REUSED", value]
        data["used"] = True
        self.values[key] = json.dumps(data, separators=(",", ":"))
        return ["OK", value]

    async def set_values_with_ttl(
        self, entries: Sequence[tuple[str, str, int]]
    ) -> None:
        if not entries:
            return
        for key, value, ttl_seconds in entries:
            await self.set_value(key, value, ttl_seconds=ttl_seconds)

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
        self._expire_if_needed(user_sessions_key)
        previous_expiry = self.expirations.get(user_sessions_key)
        previous_ttl = (
            max(0, int(previous_expiry - time.time()))
            if previous_expiry is not None
            else 0
        )
        await self.set_value(refresh_key, refresh_value, ttl_seconds=ttl_seconds)
        await self.set_value(session_key, session_value, ttl_seconds=ttl_seconds)
        self.sets.setdefault(user_sessions_key, set()).add(session_id)
        self.expirations[user_sessions_key] = time.time() + max(
            ttl_seconds, previous_ttl, 1
        )


class FakeUserRepository(UserRepository):
    def __init__(self, user: User) -> None:
        self.user = user

    async def find_by_email_or_username(self, *, value: str) -> User:
        _ = value
        return self.user

    async def find_by_id(self, *, id: uuid.UUID) -> User | None:
        return self.user if self.user is not None and id == self.user.id else None


class FakePasswordService(PasswordService):
    def compare(self, *, password: str, hash: str) -> bool:
        return password == "password" and hash == "password-hash"


class FakeJwtService(JwtService):
    def __init__(self) -> None:
        self.claims: dict[str, dict[str, object]] = {}

    def generate_token(
        self,
        payload: dict[str, object],
        expires_in: timedelta | None = None,
    ) -> str:
        _ = expires_in
        token = f"access-{len(self.claims)}"
        self.claims[token] = payload
        return token

    def validate(self, token: str) -> dict[str, object]:
        return self.claims[token]

    def decode(self, token: str) -> dict[str, object]:
        return self.claims[token]

    def decode_token(self, token: str, *, verify_exp: bool = True) -> dict[str, object]:
        _ = verify_exp
        return self.claims[token]

    def decode_ignoring_expiry(self, token: str) -> dict[str, object]:
        return self.claims[token]


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@pytest.fixture(autouse=True)
def stable_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        refresh_expiry_days=1,
        refresh_max_session_days=30,
        jwt_access_expiry_minutes=15,
        jwt_secret="test-secret-for-unit-tests-32-bytes-min",
        jwt_issuer="test-issuer",
        jwt_audience="test-audience",
    )
    for module in (
        "record.app.auth.refresh_token_service",
        "record.app.auth.token_blacklist_service",
        "record.app.auth.jwt_service",
    ):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings, raising=False)


def _build_services(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    MemoryRedis, RefreshTokenService, TokenBlacklistService, AuthService, FakeJwtService
]:
    redis = MemoryRedis()
    refresh_service = RefreshTokenService(redis)
    blacklist_service = TokenBlacklistService(redis)
    user = User(
        username="testuser",
        email="testuser@example.com",
        password="password-hash",
    )
    jwt_service = FakeJwtService()
    auth_service = AuthService(
        user_repository=FakeUserRepository(user),
        password_service=FakePasswordService(),
        jwt_service=jwt_service,
        refresh_token_service=refresh_service,
        token_blacklist_service=blacklist_service,
    )
    return redis, refresh_service, blacklist_service, auth_service, jwt_service


def _request_with_cookie(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"cookie", f"access_token={token}".encode())],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
        }
    )


def test_login_and_refresh_rotate_token_within_same_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, _, _, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        first_session_id = jwt_service.claims[access_token]["sid"]
        rotated_access, rotated_refresh = await auth_service.refresh(refresh_token)
        assert rotated_refresh != refresh_token
        assert jwt_service.claims[rotated_access]["sid"] == first_session_id
        assert await redis.key_exists(f"session:{first_session_id}")

    asyncio.run(run())


def test_replayed_used_token_revokes_session_and_blacklists_sid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, _, blacklist, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        session_id = str(jwt_service.claims[access_token]["sid"])
        await auth_service.refresh(refresh_token)
        with pytest.raises(TokenReuseDetectedException):
            await auth_service.refresh(refresh_token)
        assert not await redis.key_exists(f"session:{session_id}")
        assert await blacklist.is_revoked(session_id)

    asyncio.run(run())


def test_second_rotation_with_same_token_is_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, refresh_service, _, _, _ = _build_services(monkeypatch)

    async def run() -> None:
        issued = await refresh_service.issue("user-id")
        outcomes = await asyncio.gather(
            refresh_service.rotate(issued.token),
            refresh_service.rotate(issued.token),
            return_exceptions=True,
        )
        assert sum(not isinstance(result, BaseException) for result in outcomes) == 1
        assert (
            sum(isinstance(result, TokenReuseDetectedException) for result in outcomes)
            == 1
        )

    asyncio.run(run())


def test_logout_invalidates_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, blacklist, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        claims = jwt_service.claims[access_token]
        await auth_service.logout(refresh_token, claims)
        with pytest.raises(TokenInvalidException):
            await get_current_user(
                _request_with_cookie(access_token),
                jwt_service,
                blacklist,
            )

    asyncio.run(run())


def test_logout_all_revokes_and_blacklists_every_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, _, blacklist, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_a, _ = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        access_b, _ = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        session_ids = {
            str(jwt_service.claims[access_a]["sid"]),
            str(jwt_service.claims[access_b]["sid"]),
        }
        user_id = str(jwt_service.claims[access_a]["sub"])
        await auth_service.logout_all(user_id)
        assert await redis.set_members(f"user_sessions:{user_id}") == set()
        for session_id in session_ids:
            assert await blacklist.is_revoked(session_id)

    asyncio.run(run())


def test_expired_refresh_record_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, refresh_service, _, _, _ = _build_services(monkeypatch)

    async def run() -> None:
        issued = await refresh_service.issue("user-id")
        token_hash = _h(issued.token)
        key = f"refresh:{token_hash}"
        value = await redis.get_value(key)
        assert value is not None
        data = json.loads(value)
        data["expires_at"] = time.time() - 1
        redis.values[key] = json.dumps(data)
        with pytest.raises(TokenInvalidException):
            await refresh_service.rotate(issued.token)

    asyncio.run(run())


def test_unknown_refresh_token_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, refresh_service, _, _, _ = _build_services(monkeypatch)

    async def run() -> None:
        with pytest.raises(TokenInvalidException):
            await refresh_service.rotate("not-a-known-token")

    asyncio.run(run())


def test_auth_dependency_rejects_revoked_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, blacklist, _, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        session_id = "revoked-session"
        token = jwt_service.generate_token({"sub": "user-id", "sid": session_id})
        await blacklist.revoke_session(session_id)
        with pytest.raises(TokenInvalidException):
            await get_current_user(
                _request_with_cookie(token),
                jwt_service,
                blacklist,
            )

    asyncio.run(run())


def test_auth_dependency_rejects_access_token_without_sid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, blacklist, _, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        token = jwt_service.generate_token({"sub": "user-id"})
        with pytest.raises(TokenInvalidException):
            await get_current_user(
                _request_with_cookie(token),
                jwt_service,
                blacklist,
            )

    asyncio.run(run())


def test_logout_with_only_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, _, blacklist, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        session_id = str(jwt_service.claims[access_token]["sid"])
        # Logout without access token (simulating expired/missing cookie)
        await auth_service.logout(refresh_token, None)
        assert not await redis.key_exists(f"session:{session_id}")
        assert await blacklist.is_revoked(session_id)

    asyncio.run(run())


def test_logout_with_only_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, _, blacklist, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        session_id = str(jwt_service.claims[access_token]["sid"])
        token_hash = _h(refresh_token)
        assert await redis.key_exists(f"refresh:{token_hash}")

        # Logout with only access claims, no refresh token
        claims = jwt_service.claims[access_token]
        await auth_service.logout(None, claims)
        # Verify the refresh token and session are revoked in Redis!
        assert not await redis.key_exists(f"refresh:{token_hash}")
        assert not await redis.key_exists(f"session:{session_id}")
        assert await blacklist.is_revoked(session_id)

    asyncio.run(run())


def test_logout_with_different_sessions_revokes_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, _, blacklist, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_a, refresh_a = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        access_b, refresh_b = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        sid_a = str(jwt_service.claims[access_a]["sid"])
        sid_b = str(jwt_service.claims[access_b]["sid"])
        assert sid_a != sid_b

        # Pass refresh token from session A and access claims from session B
        claims_b = jwt_service.claims[access_b]
        await auth_service.logout(refresh_a, claims_b)

        # Both sessions must be revoked and blacklisted
        assert not await redis.key_exists(f"session:{sid_a}")
        assert not await redis.key_exists(f"session:{sid_b}")
        assert await blacklist.is_revoked(sid_a)
        assert await blacklist.is_revoked(sid_b)

    asyncio.run(run())


def test_logout_all_with_empty_sessions_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, auth_service, _ = _build_services(monkeypatch)

    async def run() -> None:
        # User with no active sessions
        await auth_service.logout_all("user-with-no-sessions")

    asyncio.run(run())


def test_noscript_error_reload_and_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, refresh_service, _, _, _ = _build_services(monkeypatch)

    async def run() -> None:
        issued = await refresh_service.issue("user-id")
        orig_eval = redis.eval_sha
        first_call = True
        load_script_calls = 0
        orig_load_script = redis.load_script

        async def counted_load_script(script: str) -> str:
            nonlocal load_script_calls
            load_script_calls += 1
            return await orig_load_script(script)

        redis.load_script = counted_load_script

        async def failing_eval_sha(sha: str, key: str) -> object:
            nonlocal first_call
            if first_call:
                first_call = False
                raise NoScriptError("NOSCRIPT")
            return await orig_eval(sha, key)

        redis.eval_sha = failing_eval_sha
        res = await refresh_service.rotate(issued.token)
        assert res.user_id == "user-id"
        assert load_script_calls == 2

    asyncio.run(run())


def test_session_started_at_and_absolute_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, refresh_service, _, auth_service, jwt_service = _build_services(monkeypatch)
    # Set max_session_days to 10 days
    refresh_service.max_session_seconds = 100

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "user", "password": "password"}
        )
        # First rotation within cap succeeds
        _, rotated_refresh = await auth_service.refresh(refresh_token)

        # Fast forward time beyond absolute cap
        token_hash = _h(rotated_refresh)
        raw = await redis.get_value(f"refresh:{token_hash}")
        data = json.loads(raw)
        data["session_started_at"] = time.time() - 200
        redis.values[f"refresh:{token_hash}"] = json.dumps(data)

        # Rotation must now be rejected
        with pytest.raises(TokenInvalidException):
            await auth_service.refresh(rotated_refresh)

    asyncio.run(run())


def test_redis_error_exception_handler() -> None:
    request = _request_with_cookie("dummy")
    response = asyncio.run(
        redis_exception_handler(request, RedisError("Redis connection lost"))
    )
    assert response.status_code == 503
    body = json.loads(response.body.decode())
    assert body["status"] == "error"


def test_router_refresh_has_get_pg_session_dependency() -> None:
    from record.app.auth.router import router
    from record.db.sql.postgres.session import get_pg_session

    refresh_route = [
        r for r in router.routes if getattr(r, "path", None) == "/auth/refresh"
    ][0]
    dep_funcs = [d.dependency for d in refresh_route.dependencies]
    assert get_pg_session in dep_funcs


def test_router_logout_optional_token_and_cookie_cleared() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, MagicMock
    from record.app.auth.router import router
    from record.app.shared.dependencies import get_auth_service

    app = FastAPI()
    app.include_router(router)
    mock_auth = MagicMock()
    mock_auth.logout = AsyncMock()
    app.dependency_overrides[get_auth_service] = lambda: mock_auth

    client = TestClient(app)
    # Logout with only refresh cookie and no access token succeeds
    client.cookies.set("refresh_token", "sample-refresh-token", path="/auth")
    res = client.post("/auth/logout")
    assert res.status_code == 200
    mock_auth.logout.assert_called_once_with("sample-refresh-token", None)
    cookies = res.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert any(
        re.search(r"Path=/auth(;|$)", c) for c in cookies if "refresh_token" in c
    )
    assert any(re.search(r"Path=/(;|$)", c) for c in cookies if "access_token" in c)


def test_router_login_and_refresh_cookies_path_and_preservation() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, MagicMock
    from record.app.auth.router import router
    from record.app.shared.dependencies import get_auth_service
    from record.db.sql.postgres.session import get_pg_session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pg_session] = lambda: None
    mock_auth = MagicMock()
    mock_auth.login = AsyncMock(return_value=("acc_tok", "ref_tok"))
    mock_auth.refresh = AsyncMock(return_value=("new_acc_tok", "new_ref_tok"))
    app.dependency_overrides[get_auth_service] = lambda: mock_auth

    client = TestClient(app)
    res_login = client.post(
        "/auth/login", json={"user": "testuser", "password": "password123"}
    )
    assert res_login.status_code == 200
    login_cookies = res_login.headers.get_list("set-cookie")
    assert len(login_cookies) == 2
    assert any(
        "access_token=acc_tok" in c and re.search(r"Path=/(;|$)", c)
        for c in login_cookies
    )
    assert any(
        "refresh_token=ref_tok" in c and re.search(r"Path=/auth(;|$)", c)
        for c in login_cookies
    )

    client.cookies.set("refresh_token", "ref_tok", path="/auth")
    res_refresh = client.post("/auth/refresh")
    assert res_refresh.status_code == 200
    refresh_cookies = res_refresh.headers.get_list("set-cookie")
    assert len(refresh_cookies) == 2
    assert any(
        "access_token=new_acc_tok" in c and re.search(r"Path=/(;|$)", c)
        for c in refresh_cookies
    )
    assert any(
        "refresh_token=new_ref_tok" in c and re.search(r"Path=/auth(;|$)", c)
        for c in refresh_cookies
    )


def test_router_logout_all_requires_auth() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from record.app.auth.router import router
    from record.handlers.exception_handler import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    client = TestClient(app)
    res = client.post("/auth/logout-all")
    assert res.status_code == 401


def test_session_started_at_preserved_across_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, _, _, auth_service, _ = _build_services(monkeypatch)

    async def run() -> None:
        _, refresh_token = await auth_service.login(
            data={"user": "u", "password": "password"}
        )
        started = json.loads(await redis.get_value(f"refresh:{_h(refresh_token)}"))[
            "session_started_at"
        ]
        _, rotated_token = await auth_service.refresh(refresh_token)
        assert (
            json.loads(await redis.get_value(f"refresh:{_h(rotated_token)}"))[
                "session_started_at"
            ]
            == started
        )

    asyncio.run(run())


def test_refresh_fails_after_logout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "u", "password": "password"}
        )
        await auth_service.logout(refresh_token, jwt_service.claims[access_token])
        with pytest.raises(TokenInvalidException):
            await auth_service.refresh(refresh_token)

    asyncio.run(run())


def test_logout_all_invalidates_old_refresh_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_a, refresh_a = await auth_service.login(
            data={"user": "u", "password": "password"}
        )
        _, refresh_b = await auth_service.login(
            data={"user": "u", "password": "password"}
        )
        user_id = str(jwt_service.claims[access_a]["sub"])
        await auth_service.logout_all(user_id)
        for token in (refresh_a, refresh_b):
            with pytest.raises(TokenInvalidException):
                await auth_service.refresh(token)

    asyncio.run(run())


def test_refresh_for_deleted_user_fails_and_blacklists_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, blacklist, auth_service, jwt_service = _build_services(monkeypatch)

    async def run() -> None:
        access_token, refresh_token = await auth_service.login(
            data={"user": "u", "password": "password"}
        )
        session_id = str(jwt_service.claims[access_token]["sid"])
        auth_service.user_repository.user = None
        with pytest.raises(TokenInvalidException):
            await auth_service.refresh(refresh_token)
        assert await blacklist.is_revoked(session_id)

    asyncio.run(run())


def test_optional_user_returns_none_for_token_without_sid() -> None:
    jwt_svc = JwtService()
    token = jwt_svc.generate_token({"sub": "user-without-sid"})
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"access_token={token}".encode())],
        }
    )
    assert asyncio.run(get_optional_current_user(request, jwt_svc)) is None


def test_optional_user_accepts_expired_token() -> None:
    jwt_svc = JwtService()
    expired_token = jwt_svc.jwt.encode(
        {
            "sub": "user-expired",
            "sid": "session-expired",
            "exp": time.time() - 3600,
            "iat": time.time() - 7200,
            "iss": jwt_svc.settings.iss,
            "aud": jwt_svc.settings.aud,
            "jti": "abc",
        },
        jwt_svc.settings.secret,
        algorithm="HS256",
    )

    req_expired = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"access_token={expired_token}".encode())],
        }
    )
    claims = asyncio.run(get_optional_current_user(req_expired, jwt_svc))
    assert claims == {"sub": "user-expired", "sid": "session-expired"}

    req_corrupt = Request(
        {"type": "http", "headers": [(b"cookie", b"access_token=badtoken")]}
    )
    claims_bad = asyncio.run(get_optional_current_user(req_corrupt, jwt_svc))
    assert claims_bad is None
