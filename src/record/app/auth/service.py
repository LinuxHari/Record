from typing import TypedDict
from record.app.auth.password_service import PasswordService
from record.app.auth.jwt_service import JwtService
from record.app.auth.refresh_token_service import RefreshTokenService
from record.app.user.repository import UserRepository
from record.app.user.models import User
from record.exceptions.http_excpetions import BadRequestException


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
    ):
        self.user_repository = user_repository
        self.password_service = password_service
        self.jwt_service = jwt_service
        self.refresh_token_service = refresh_token_service

    async def sign_up(self, *, data: SignupData) -> None:
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

        access_token = self.jwt_service.generate_token(payload={"sub": str(user.id)})
        refresh_token = self.refresh_token_service.generate_token()

        return access_token, refresh_token