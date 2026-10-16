from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from typing_extensions import Self

from record.app.auth.service import AuthService
from record.app.shared.dependencies import (
    AccessClaims,
    get_auth_service,
    get_current_user,
    get_optional_current_user,
)
from record.app.shared.validators import (
    email_validator,
    password_validator,
    username_validator,
)
from record.config import Settings
from record.db.sql.postgres.session import get_pg_session
from record.dependencies import get_settings
from record.exceptions.custom_exceptions import TokenInvalidException
from record.handlers.response_handler import GlobalResponseHandler

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    route_class=GlobalResponseHandler,
)

# The refresh cookie is only sent to the auth routes.
REFRESH_COOKIE_PATH = "/auth"

PasswordString = Annotated[
    str,
    Field(
        title="Password",
        description="Password must contain at least 8 characters including one lowercase, one uppercase, one special character, and one number",
        min_length=password_validator.min_len,
        max_length=password_validator.max_len,
    ),
    AfterValidator(password_validator.validate),
]

UsernameString = Annotated[
    str,
    Field(
        title="Username",
        description="Username can only contain lowercase and numbers",
        min_length=username_validator.min_len,
        max_length=username_validator.max_len,
        examples=["johndoe"],
    ),
    AfterValidator(username_validator.validate),
]

EmailString = Annotated[
    str,
    Field(
        title="Email",
        description="Email can be any typical email",
        examples=["user@example.com"],
        min_length=email_validator.min_len,
        max_length=email_validator.max_len,
    ),
    AfterValidator(email_validator.validate),
]


class SignupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: UsernameString
    email: EmailString
    password: PasswordString
    confirm_password: str = Field(
        title="Confirm password",
        description="Confirm password must be same as password",
    )

    @model_validator(mode="after")
    def validate_confirm_password(self) -> Self:
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(
        title="user",
        description="Username or email that was given while signing up",
    )
    password: str = Field(
        title="Password", description="Password that was given while signing up."
    )


def _set_auth_cookies(
    response: Response, settings: Settings, access_token: str, refresh_token: str
) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.jwt_access_expiry_minutes * 60,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.refresh_expiry_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="lax",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key="access_token", httponly=True, secure=True, samesite="lax"
    )
    response.delete_cookie(
        key="refresh_token",
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="lax",
    )


@router.post(
    "/register",
    dependencies=[Depends(get_pg_session, scope="function")],
)
async def signup(
    payload: SignupPayload,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    await auth_service.sign_up(
        data={
            "username": payload.username,
            "password": payload.password,
            "email": payload.email,
        }
    )


@router.post(
    "/login",
    dependencies=[Depends(get_pg_session, scope="function")],
)
async def login(
    response: Response,
    payload: LoginPayload,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> None:
    access_token, refresh_token = await auth_service.login(
        data={"user": payload.user, "password": payload.password}
    )

    _set_auth_cookies(response, settings, access_token, refresh_token)


@router.post("/logout")
async def logout(
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias="refresh_token"),
    access_claims: AccessClaims | None = Depends(get_optional_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.logout(refresh_cookie, access_claims)

    _clear_auth_cookies(response)
    return {"message": "User logged out successfully"}


@router.post(
    "/refresh",
    dependencies=[Depends(get_pg_session, scope="function")],
)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias="refresh_token"),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not refresh_cookie:
        raise TokenInvalidException()

    client_ip = request.client.host if request.client else None
    access_token, new_refresh_token = await auth_service.refresh(
        refresh_cookie, client_ip=client_ip
    )

    _set_auth_cookies(response, settings, access_token, new_refresh_token)
    return {"access_token": access_token}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    access_claims: AccessClaims = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.logout_all(access_claims["sub"])

    _clear_auth_cookies(response)
    return {"message": "User logged out successfully"}