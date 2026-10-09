from ..db.sql_repository import SqlRepository
from .models import User

class UserRepository(SqlRepository):
    def __init__(self):
        super().__init__(User)

    def find_by_username(self, session, username: str) -> User | None:
        return self.get_by_field(session, "username", username)

    def find_by_email(self, session, email: str) -> User | None:
        return self.get_by_field(session, "email", email)

user_repository = UserRepository()