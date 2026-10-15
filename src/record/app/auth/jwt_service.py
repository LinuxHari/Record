import uuid
from datetime import datetime, timedelta, timezone
from jwt import PyJWT
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel
from typing import TypedDict, Literal

from record.dependencies import get_settings
from record.exceptions.custom_exceptions import TokenExpiredException, TokenInvalidException

class JwtSettings(BaseModel):
    secret: str
    iss: str
    aud: str
    exp_mins: int

class JwtValidationReturn(TypedDict):
    status: Literal["expired", "invalid", "valid"]
    payload: dict | None

class JwtService:
    ALGORITHM = "HS256"
    LEEWAY_SECONDS = 10

    def __init__(self):
        app_settings = get_settings()
        self.settings = JwtSettings(
            secret=app_settings.jwt_secret,
            iss=str(app_settings.jwt_issuer),
            aud=str(app_settings.jwt_audience),
            exp_mins=app_settings.jwt_access_expiry_minutes
        )
        self.jwt: PyJWT = PyJWT(
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_iat": True,
                "verify_jti": True,
                "require": ["exp", "iat", "iss", "aud", "jti"],
            }
        )

    def generate_token(
        self, payload: dict, expires_in: timedelta | None = None
    ) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            **payload,
            "iss": self.settings.iss,
            "aud": self.settings.aud,
            "iat": now,
            "exp": now
            + (
                expires_in
                if expires_in is not None
                else timedelta(minutes=self.settings.exp_mins)
            ),
            "jti": str(uuid.uuid4()),
        }

        return self.jwt.encode(claims, self.settings.secret, algorithm=self.ALGORITHM)

    def decode(self, token: str) -> dict:
        claims = self.jwt.decode(
            token,
            self.settings.secret,
            algorithms=[self.ALGORITHM],
            audience=self.settings.aud,
            issuer=self.settings.iss,
            leeway=self.LEEWAY_SECONDS,
        )

        return claims

    def validate(self, token: str) -> JwtValidationReturn:
        try:
            payload = self.decode(token)
            return payload

        except ExpiredSignatureError:
            raise TokenExpiredException()

        except (InvalidTokenError, KeyError, ValueError):
            return TokenInvalidException()
