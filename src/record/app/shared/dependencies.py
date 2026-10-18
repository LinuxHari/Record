from functools import lru_cache

from fastapi import Depends, Request
from jwt.exceptions import InvalidTokenError

from record.app.auth.service import AccessClaims, AuthService
from record.app.auth.password_service import PasswordService
from record.app.auth.jwt_service import JwtService
from record.app.auth.refresh_token_service import RefreshTokenService
from record.app.auth.token_blacklist_service import TokenBlacklistService
from record.app.user.service import UserService
from record.app.user.repository import UserRepository
from record.app.assets.service import AssetService
from record.db.sql.postgres.session import get_pg_context
from record.db.memory.redis.cache_service import get_cache_service
from record.db.memory.redis.service import RedisService
from record.exceptions.custom_exceptions import TokenInvalidException

__all__ = ["AccessClaims"]


def get_user_repository() -> UserRepository:
    return UserRepository(get_pg_context)


@lru_cache(maxsize=None)
def get_password_service() -> PasswordService:
    return PasswordService()


@lru_cache(maxsize=None)
def get_jwt_service() -> JwtService:
    return JwtService()


def get_cache_redis() -> RedisService:
    return get_cache_service()


@lru_cache(maxsize=None)
def _build_refresh_token_service(redis: RedisService) -> RefreshTokenService:
    return RefreshTokenService(redis)


@lru_cache(maxsize=None)
def _build_token_blacklist_service(redis: RedisService) -> TokenBlacklistService:
    return TokenBlacklistService(redis)


def get_refresh_token_service(
    redis: RedisService = Depends(get_cache_redis),
) -> RefreshTokenService:
    return _build_refresh_token_service(redis)


def get_token_blacklist_service(
    redis: RedisService = Depends(get_cache_redis),
) -> TokenBlacklistService:
    return _build_token_blacklist_service(redis)


def _extract_access_token(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if token:
        return token

    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and credentials:
        return credentials
    return None


async def get_current_user(
    request: Request,
    jwt_service: JwtService = Depends(get_jwt_service),
    token_blacklist_service: TokenBlacklistService = Depends(
        get_token_blacklist_service
    ),
) -> AccessClaims:
    token = _extract_access_token(request)
    if token is None:
        raise TokenInvalidException()

    claims = jwt_service.validate(token)
    subject = claims.get("sub")
    session_id = claims.get("sid")
    if not isinstance(subject, str) or not isinstance(session_id, str):
        raise TokenInvalidException()

    if await token_blacklist_service.is_revoked(session_id):
        raise TokenInvalidException()

    return {"sub": subject, "sid": session_id}


async def get_optional_current_user(
    request: Request,
    jwt_service: JwtService = Depends(get_jwt_service),
) -> AccessClaims | None:
    token = _extract_access_token(request)
    if token is None:
        return None

    try:
        claims = jwt_service.decode_token(token, verify_exp=False)
    except InvalidTokenError:
        return None

    subject = claims.get("sub")
    session_id = claims.get("sid")
    if not isinstance(subject, str) or not isinstance(session_id, str):
        return None
    return {"sub": subject, "sid": session_id}


def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
    password_service: PasswordService = Depends(get_password_service),
    jwt_service: JwtService = Depends(get_jwt_service),
    refresh_token_service: RefreshTokenService = Depends(get_refresh_token_service),
    token_blacklist_service: TokenBlacklistService = Depends(
        get_token_blacklist_service
    ),
) -> AuthService:
    return AuthService(
        user_repository=user_repository,
        password_service=password_service,
        jwt_service=jwt_service,
        refresh_token_service=refresh_token_service,
        token_blacklist_service=token_blacklist_service,
    )


def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repository=user_repository)

def get_asset_service() -> AssetService:
    return AssetService()