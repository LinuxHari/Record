from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.elements import ColumnElement
from typing import Generic, Sequence, TypeVar, Any
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
        limit: int = None,
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

    async def _update_many(
        self,
        session: AsyncSession,
        data: dict[str, Any],
        where: Sequence[ColumnElement[bool]],
        commit: bool = True,
    ):
        rows = await self._find_many(session, where=where)

        if rows is None:
            return None

        for row in rows:
            for key, value in data.items():
                setattr(row, key, value)

        await self._save(session, commit=commit)
        return rows

    async def _update(
        self,
        session: AsyncSession,
        data: dict[str, Any],
        where: Sequence[ColumnElement[bool]],
        commit: bool = True,
    ):
        row = await self._find_one(session, where=where)

        if row is None:
            return None

        for key, value in data.items():
            setattr(row, key, value)

        await self._save(session, commit=commit)
        return row

    async def _delete(
        self,
        session: AsyncSession,
        where: Sequence[ColumnElement[bool]],
        commit: bool = True,
    ) -> ModelT | None:
        row = await self._find_one(session, where=where)

        if row is None:
            return None

        await session.delete(row)
        await self._save(session, commit=commit)
        return row

    async def _delete_many(
        self,
        session: AsyncSession,
        where: Sequence[ColumnElement[bool]],
        commit: bool = True,
    ) -> Sequence[ModelT]:
        rows = await self._find_many(session, where=where)

        for row in rows:
            await session.delete(row)

        await self._save(session, commit=commit)
        return rows
