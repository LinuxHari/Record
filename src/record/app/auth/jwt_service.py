import uuid
from datetime import datetime, timedelta, timezone

from jwt import PyJWT
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel

from record.dependencies import get_settings
from record.exceptions.custom_exceptions import (
    TokenExpiredException,
    TokenInvalidException,
)


class JwtSettings(BaseModel):
    secret: str
    iss: str
    aud: str
    exp_mins: int


class JwtService:
    ALGORITHM = "HS256"
    LEEWAY_SECONDS = 10

    def __init__(self) -> None:
        app_settings = get_settings()
        self.settings = JwtSettings(
            secret=app_settings.jwt_secret,
            iss=str(app_settings.jwt_issuer),
            aud=str(app_settings.jwt_audience),
            exp_mins=app_settings.jwt_access_expiry_minutes,
        )
        self.jwt = PyJWT(
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_iat": True,
                "require": ["exp", "iat", "iss", "aud", "jti"],
            }
        )

    def generate_token(
        self, payload: dict[str, object], expires_in: timedelta | None = None
    ) -> str:
        now = datetime.now(timezone.utc)
        lifetime = (
            expires_in
            if expires_in is not None
            else timedelta(minutes=self.settings.exp_mins)
        )
        claims = {
            **payload,
            "iss": self.settings.iss,
            "aud": self.settings.aud,
            "iat": now,
            "exp": now + lifetime,
            "jti": str(uuid.uuid4()),
        }
        return self.jwt.encode(claims, self.settings.secret, algorithm=self.ALGORITHM)

    def decode_token(
        self, token: str, *, verify_exp: bool = True
    ) -> dict[str, object]:
        """Signature, issuer and audience are always verified.
        verify_exp=False is only for flows like logout that accept expired tokens."""
        return self.jwt.decode(
            token,
            self.settings.secret,
            algorithms=[self.ALGORITHM],
            audience=self.settings.aud,
            issuer=self.settings.iss,
            leeway=self.LEEWAY_SECONDS,
            options={"verify_exp": verify_exp},
        )

    def validate(self, token: str) -> dict[str, object]:
        try:
            return self.decode_token(token)
        except ExpiredSignatureError:
            raise TokenExpiredException()
        except InvalidTokenError:
            raise TokenInvalidException()