from fastapi import APIRouter, Depends
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
from record.app.shared.container import auth_service
from record.app.shared.validators import (
    email_validator,
    password_validator,
    username_validator,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

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

UsernameString = Annotated[str, Field(
        title="Username",
        description="Username can only contain lowercase and numbers",
        min_length=username_validator.min_len,
        max_length=username_validator.max_len,
        examples=["johndoe"],
    ), AfterValidator(username_validator.validate)]

EmailString = Annotated[str, Field(
        title="Email",
        description="Email can be any typical email",
        examples=["user@example.com"],
        min_length=email_validator.min_len,
        max_length=email_validator.max_len,
    ), AfterValidator(email_validator.validate)]

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


@router.post(
    "/register",
    dependencies=[Depends(get_pg_session, scope="function")],
)
async def signup(payload: SignupPayload) -> None:
    await auth_service.sign_up(
        data={
            "username": payload.username,
            "password": payload.password,
            "email": payload.email,
        }
    )

    return None


@router.post("/login")
def login():
    return {"message": "User logged in successfully"}


@router.post("/logout")
def logout():
    return {"message": "User logged out successfully"}


@router.get("/refresh")
def refresh_token():
    return {"message": "Token refreshed successfully"}
