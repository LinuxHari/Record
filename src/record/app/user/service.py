from typing import TypedDict

class UserData(TypedDict):
    username: str
    password: str
    email: str

class UserService:
    def __init__(self, *, user_repository):
        self.user_repository = user_repository