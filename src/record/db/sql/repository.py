from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.elements import ColumnElement
from typing import Any, Callable, Generic, Sequence, TypeVar
from sqlalchemy import select

ModelT = TypeVar("ModelT", bound=DeclarativeBase)


class BaseRepository(Generic[ModelT]):
    def __init__(
        self, model: type[ModelT], context_fn: Callable[[], AsyncSession]
    ):
        self._model = model
        self._context_fn = context_fn

    @property
    def session(self) -> AsyncSession:
        return self._context_fn()

    async def _find_one(
        self,
        *,
        where: Sequence[ColumnElement[bool]],
        columns: Sequence[ColumnElement[str]] = None,
    ) -> ModelT:
        if columns:
            stmt = select(*columns).where(*where)
        else:
            stmt = select(self._model).where(*where)

        return (await self.session.scalars(stmt)).first()

    async def _find_many(
        self,
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

        result = (await self.session.scalars(stmt)).all()
        return result

    async def _create(self, data: Sequence[ModelT]):
        self.session.add_all(data)
        return data

    async def _update_many(
        self,
        data: dict[str, Any],
        where: Sequence[ColumnElement[bool]],
    ):
        rows = await self._find_many(where=where)

        if rows is None:
            return None

        for row in rows:
            for key, value in data.items():
                setattr(row, key, value)

        return rows

    async def _update(
        self,
        data: dict[str, Any],
        where: Sequence[ColumnElement[bool]],
    ):
        row = await self._find_one(where=where)

        if row is None:
            return None

        for key, value in data.items():
            setattr(row, key, value)

        return row

    async def _delete(
        self,
        where: Sequence[ColumnElement[bool]],
    ) -> ModelT | None:
        row = await self._find_one(where=where)

        if row is None:
            return None

        await self.session.delete(row)
        return row

    async def _delete_many(
        self,
        where: Sequence[ColumnElement[bool]],
    ) -> Sequence[ModelT]:
        rows = await self._find_many(where=where)

        for row in rows:
            await self.session.delete(row)

        return rows
