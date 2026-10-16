from fastapi import Depends

from record.app.auth.service import AuthService
from record.app.auth.password_service import PasswordService
from record.app.auth.jwt_service import JwtService
from record.app.auth.refresh_token_service import RefreshTokenService
from record.app.user.service import UserService
from record.app.user.repository import UserRepository
from record.db.sql.postgres.session import get_pg_context
from record.db.memory.redis.cache_service import get_cache_service
from record.db.memory.redis.service import RedisService


def get_user_repository() -> UserRepository:
    return UserRepository(get_pg_context)


def get_password_service() -> PasswordService:
    return PasswordService()


def get_jwt_service() -> JwtService:
    return JwtService()


def get_refresh_token_service() -> RefreshTokenService:
    return RefreshTokenService()


def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
    password_service: PasswordService = Depends(get_password_service),
    jwt_service: JwtService = Depends(get_jwt_service),
    refresh_token_service: RefreshTokenService = Depends(get_refresh_token_service),
) -> AuthService:
    return AuthService(
        user_repository=user_repository,
        password_service=password_service,
        jwt_service=jwt_service,
        refresh_token_service=refresh_token_service,
    )


def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repository=user_repository)


def get_cache_redis() -> RedisService:
    return get_cache_service()
