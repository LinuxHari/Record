from typing import TypedDict
from record.app.user.repository import UserRepository
from record.app.user.models import User

class SignupData(TypedDict):
    username: str
    password: str
    email: str

class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def sign_up(self, *, data: SignupData) -> bool:
        user = User(
            username=data["username"],
            password=data["password"],
            email=data["email"],
        )
        return bool(await self.user_repository.create(user))