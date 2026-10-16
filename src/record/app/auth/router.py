from fastapi import APIRouter, Depends, Response
from typing_extensions import Self
from typing import Annotated
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    AfterValidator,
    model_validator,
)
from record.db.sql.postgres.session import get_pg_session
from record.app.auth.service import AuthService
from record.app.shared.dependencies import get_auth_service
from record.app.shared.validators import (
    email_validator,
    password_validator,
    username_validator,
)
from record.handlers.response_handler import GlobalResponseHandler
from record.config import Settings
from record.dependencies import get_settings

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    route_class=GlobalResponseHandler,
)

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
        description="Username or email that was given while signing up, it is optional if email is given",
    )
    password: str = Field(
        title="Password", description="Password that was given while signing up."
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

    return None


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
        httponly=True,
        secure=True,
        samesite="lax",
    )

    return None


@router.post("/logout")
def logout():
    return {"message": "User logged out successfully"}


@router.get("/refresh")
def refresh_token():
    return {"message": "Token refreshed successfully"}
