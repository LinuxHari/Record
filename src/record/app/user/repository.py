from typing import Callable, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from record.db.sql.repository import BaseRepository
from record.db.sql.exceptions import db_exceptions
from record.app.user.models import User

class UserRepository(BaseRepository[User]):
    def __init__(self, context_fn: Callable[[], AsyncSession]):
        super().__init__(User, context_fn)

    async def find_by_id(self, *, id: UUID) -> User | None:
        return await self._find_one(where=(self._model.id == id,))

    async def find_by_username(self, *, username: str) -> User | None:
        return await self._find_one(where=(self._model.username == username,))

    async def find_by_email(self, *, email: str) -> User | None:
        return await self._find_one(where=(self._model.email == email,))

    @db_exceptions("Creating user record")
    async def create(self, user: User, *, commit: bool = True):
        return await self._create([user], commit=commit)

    @db_exceptions("Creating users records")
    async def create_many(self, users: Sequence[User], *, commit: bool = True):
        return await self._create(users, commit=commit)
