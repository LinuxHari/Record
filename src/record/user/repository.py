from sqlalchemy.ext.asyncio import AsyncSession

from ..db.sql.repository import SqlRepository
from .models import User

class UserRepository(SqlRepository):
    def __init__(self):
        super().__init__(User)

    async def get_by_username(self, session: AsyncSession, username: str) -> User | None:
        return await self.get_by_field(session, field_filter={"field": "username", "value": username})

    async def get_by_email(self, session: AsyncSession, email: str) -> User | None:
        return await self.get_by_field(session, field_filter={"field": "email", "value": email})

user_repository = UserRepository()