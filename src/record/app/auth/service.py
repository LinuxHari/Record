from typing import TypedDict
from record.app.auth.password_service import PasswordService
from record.app.user.repository import UserRepository
from record.app.user.models import User

class SignupData(TypedDict):
    username: str
    password: str
    email: str

class AuthService:
    def __init__(self, *, user_repository: UserRepository, password_service: PasswordService):
        self.user_repository = user_repository
        self.password_service = password_service

    async def sign_up(self, *, data: SignupData) -> None:
        user = User(
            username=data["username"],
            password=self.password_service.hash(data["password"]),
            email=data["email"],
        )
        await self.user_repository.create(user)
