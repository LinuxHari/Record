import logging
import uuid
from typing import TypedDict

from record.app.auth.password_service import PasswordService
from record.app.auth.jwt_service import JwtService
from record.app.auth.refresh_token_service import RefreshTokenService
from record.app.auth.token_blacklist_service import TokenBlacklistService
from record.app.user.repository import UserRepository
from record.app.user.models import User
from record.exceptions.http_excpetions import BadRequestException
from record.exceptions.custom_exceptions import (
    FieldValidationException,
    TokenInvalidException,
    TokenReuseDetectedException,
)

logger = logging.getLogger(__name__)


class AccessClaims(TypedDict):
    sub: str
    sid: str


class SignupData(TypedDict):
    username: str
    password: str
    email: str


class LoginData(TypedDict):
    user: str
    password: str


class AuthService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        password_service: PasswordService,
        jwt_service: JwtService,
        refresh_token_service: RefreshTokenService,
        token_blacklist_service: TokenBlacklistService,
    ):
        self.user_repository = user_repository
        self.password_service = password_service
        self.jwt_service = jwt_service
        self.refresh_token_service = refresh_token_service
        self.token_blacklist_service = token_blacklist_service

    async def sign_up(self, *, data: SignupData) -> None:
        existing_user = await self.user_repository.find_by_email_and_username(
            email=data["email"], username=data["username"]
        )

        if existing_user is not None:
            if data["username"] == existing_user.username:
                raise FieldValidationException(
                    field="username", detail="Username is not available"
                )
            if data["email"] == existing_user.email:
                raise FieldValidationException(
                    field="email", detail="User with given email already exists"
                )

        user = User(
            username=data["username"],
            password=self.password_service.hash(data["password"]),
            email=data["email"],
        )
        await self.user_repository.create(user)

    async def login(self, *, data: LoginData) -> tuple[str, str]:
        user = await self.user_repository.find_by_email_or_username(value=data["user"])
        if not user or not self.password_service.compare(
            password=data["password"], hash=user.password
        ):
            raise BadRequestException("Incorrect credentials. Please try again.")

        issued = await self.refresh_token_service.issue(str(user.id))
        access_token = self.jwt_service.generate_token(
            payload={"sub": str(user.id), "sid": issued.session_id}
        )
        return access_token, issued.token

    async def _kill_session(self, session_id: str, user_id: str) -> None:
        await self.refresh_token_service.revoke_session(session_id, user_id)
        await self.token_blacklist_service.revoke_session(session_id)

    async def refresh(
        self, refresh_token: str, *, client_ip: str | None = None
    ) -> tuple[str, str]:
        try:
            result = await self.refresh_token_service.rotate(refresh_token)
        except TokenReuseDetectedException as exc:
            logger.warning(
                "Refresh token reuse detected",
                extra={
                    "user_id": exc.user_id,
                    "session_id": exc.session_id,
                    "client_ip": client_ip,
                },
            )
            await self._kill_session(exc.session_id, exc.user_id)
            raise

        user = await self.user_repository.find_by_id(id=uuid.UUID(result.user_id))
        if user is None or user.deleted_at is not None:
            await self._kill_session(result.session_id, result.user_id)
            raise TokenInvalidException()

        issued = await self.refresh_token_service.issue(
            result.user_id, result.session_id, result.session_started_at
        )

        # Checked after issue() so a logout racing with this refresh cannot
        # leave a live refresh token behind.
        if await self.token_blacklist_service.is_revoked(result.session_id):
            await self.refresh_token_service.revoke_session(
                result.session_id, result.user_id
            )
            raise TokenInvalidException()

        access_token = self.jwt_service.generate_token(
            payload={"sub": result.user_id, "sid": result.session_id}
        )
        return access_token, issued.token

    async def logout(
        self,
        refresh_token: str | None,
        access_claims: AccessClaims | None = None,
    ) -> None:
        session_ids: set[str] = set()

        if refresh_token:
            session_id = await self.refresh_token_service.revoke_by_token(refresh_token)
            if session_id:
                session_ids.add(session_id)

        if access_claims:
            await self.refresh_token_service.revoke_session(
                access_claims["sid"], access_claims["sub"]
            )
            session_ids.add(access_claims["sid"])

        await self.token_blacklist_service.revoke_sessions(list(session_ids))

    async def logout_all(self, user_id: str) -> None:
        session_ids = await self.refresh_token_service.revoke_all(user_id)
        await self.token_blacklist_service.revoke_sessions(session_ids)