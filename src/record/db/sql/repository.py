from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.elements import ColumnElement
from typing import Generic, Sequence, TypeVar
from sqlalchemy import select

ModelT = TypeVar("ModelT", bound=DeclarativeBase)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT]):
        self._model = model

    @staticmethod
    async def _save(session: AsyncSession, commit: bool):
        if commit:
            await session.commit()
        else:
            await session.flush()

    async def _find_one(
        self,
        session: AsyncSession,
        *,
        where: Sequence[ColumnElement[bool]],
        columns: Sequence[ColumnElement[str]] = None,
    ) -> ModelT:
        if columns:
            stmt = select(*columns).where(*where)
        else:
            stmt = select(self._model).where(*where)

        return (await session.scalars(stmt)).first()

    async def _find_many(
        self,
        session: AsyncSession,
        *,
        where: Sequence[ColumnElement[bool]],
        columns: Sequence[str] = None,
        order_by: Sequence[str] = None,
        offset: int = None,
        limit: int = None
    ) -> ModelT:
        if columns:
            stmt = select(*columns).where(*where)
        else:
            stmt = select(self._model).where(*where)
        if order_by:
            stmt = stmt.order_by(*order_by)
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)

        result = (await session.scalars(stmt)).all()
        return result

    async def _create(
        self, session: AsyncSession, data: Sequence[ModelT], *, commit: bool = True
    ):
        session.add_all(data)
        await self._save(session, commit=commit)
        return data

    async def _update(
        self, session: AsyncSession, data: Sequence[dict], where: Sequence[ColumnElement[bool]], commit: bool = True
    ):
        for ins in data:
            row = await self._find_one(session, where=where, columns=ins.keys())
            if row is None:
                return None, ins
            for key, value in ins.items():
                setattr(row, key, value)

        self._save(session, commit=commit)
        return data