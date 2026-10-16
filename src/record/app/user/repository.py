import uuid
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import or_

from record.db.sql.repository import BaseRepository
from record.app.user.models import User

class UserRepository(BaseRepository[User]):
    def __init__(self, context_fn: Callable[[], AsyncSession]):
        super().__init__(User, context_fn)

    async def find_by_id(self, *, id: uuid.UUID) -> User | None:
        return await self._find_one(where=(self._model.id == id,))

    # async def find_by_username(self, *, username: str) -> User | None:
    #     return await self._find_one(where=(self._model.username == username,))

    async def find_by_email_or_username(self, *, value: str) -> User | None:
        return await self._find_one(
            where=((self._model.username == value) | (self._model.email == value),)
        )

    async def find_by_email_and_username(self, *, email: str, username: str) -> User | None:
        return await self._find_one(where=((self._model.username == username) | (self._model.email == email)))
    # async def find_by_email(self, *, email: str) -> User | None:
    #     return await self._find_one(where=(self._model.email == email,))

    async def create(self, user: User):
        return await self._create([user])

    # async def create_many(self, users: Sequence[User]):
    #     return await self._create(users)
