from sqlalchemy.ext.asyncio import AsyncSession
from typing import Sequence
from uuid import UUID

from record.db.sql.repository import BaseRepository
from record.db.sql.exceptions import db_exceptions
from record.app.user.models import User

class UserRepository(BaseRepository[User]):
    def __init__(self, model: type[User]):
        super().__init__(model)

    async def find_by_id(self, session: AsyncSession, *, id: UUID) -> User | None:
        return await self._find_one(session, where=(self._model.id == id,))

    async def find_by_username(self, session: AsyncSession, *, username: str) -> User | None:
        return await self._find_one(session, where=(self._model.username == username,))

    async def find_by_email(self, session: AsyncSession, *, email: str) -> User | None:
        return await self._find_one(session, where=(self._model.email == email,))

    @db_exceptions("Creating user record")
    async def create(self, session: AsyncSession, user: User, *, commit:bool = True):
        return await self._create(session, [user], commit=commit)

    @db_exceptions("Creating users records")
    async def create_many(self, session: AsyncSession, users: Sequence[User], *, commit: bool = True):
        return await self._create(session, users, commit=commit)

    @db_exceptions("Updating user record")
    async def update(self, session: AsyncSession, user: User, *, commit: bool = True):
        return await self._update(session, [user], commit=commit)

user_repository = UserRepository(User)