"""Generic async repository for SQLAlchemy 2.x (AsyncSession)."""
from __future__ import annotations

from functools import wraps
from typing import Any, Generic, Mapping, Sequence, TypeVar

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .sql_exceptions import SqlException, SqlIntegrityException, SqlNoResultException

ModelT = TypeVar("ModelT")


def db_exceptions(action: str):
    """Translate SQLAlchemy errors into the repository's own exceptions.

    - Our own exceptions (not found, unknown column, ...) pass through untouched.
    - Integrity errors -> SqlIntegrityException (after rollback).
    - Any other SQLAlchemyError -> SqlException (after rollback).
    - Non-database exceptions (programming bugs) are NOT swallowed.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, session: AsyncSession, *args, **kwargs):
            try:
                return await fn(self, session, *args, **kwargs)
            except (SqlNoResultException, SqlException):
                raise
            except IntegrityError as e:
                await session.rollback()
                raise SqlIntegrityException(f"Integrity error: {e.orig}") from e
            except SQLAlchemyError as e:
                await session.rollback()
                raise SqlException(f"Error {action}: {e}") from e

        return wrapper

    return decorator


class SqlRepository(Generic[ModelT]):

    def __init__(self, model: type[ModelT]):
        self.model = model
        self._columns = {
            attr.key: getattr(model, attr.key)
            for attr in sa_inspect(model).column_attrs
        }

    def _column(self, name: str):
        try:
            return self._columns[name]
        except KeyError:
            raise SqlException(
                f"Unknown column '{name}' on {self.model.__name__}"
            ) from None

    def _where(self, filters: Mapping[str, Any]) -> list:
        return [self._column(k) == v for k, v in filters.items()]

    def _select(
        self,
        where: Sequence,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ):
        if order_direction not in ("asc", "desc"):
            raise SqlException(f"Invalid order_direction '{order_direction}'")
        stmt = select(self.model).where(*where)
        if order_by:
            col = self._column(order_by)
            stmt = stmt.order_by(col.desc() if order_direction == "desc" else col.asc())
        return stmt.limit(limit).offset(offset)

    @staticmethod
    async def _save(session: AsyncSession, commit: bool) -> None:
        if commit:
            await session.commit()
        else:
            await session.flush()

    async def _reload(self, session: AsyncSession, ids: Sequence) -> list[ModelT]:
        """Re-read rows in ONE query, refreshing instances already in the session.

        Needed after commit(): with expire_on_commit=True, attributes are expired
        and lazy-loading them in async code raises MissingGreenlet.
        """
        stmt = (
            select(self.model)
            .where(self._column("id").in_(ids))
            .execution_options(populate_existing=True)
        )
        return list((await session.execute(stmt)).scalars().all())

    def _apply(self, record: ModelT, data: Mapping[str, Any]) -> None:
        if not data:
            raise SqlException("update_data must not be empty")
        for key in data:  # validate everything before touching the record
            self._column(key)
        for key, value in data.items():
            setattr(record, key, value)

    # CREATE

    @db_exceptions("creating record")
    async def create(self, session: AsyncSession, model_data: dict, *, commit: bool = True) -> ModelT:
        model_instance = self.model(**model_data)
        session.add(model_instance)
        await self._save(session, commit)
        await session.refresh(model_instance)
        return model_instance

    @db_exceptions("creating records")
    async def create_many(
        self, session: AsyncSession, model_data_list: list[dict], *, commit: bool = True
    ) -> list[ModelT]:
        records = [self.model(**data) for data in model_data_list]
        if not records:
            return []
        session.add_all(records)
        await session.flush()  # populates primary keys
        ids = [r.id for r in records]
        await self._save(session, commit)
        await self._reload(session, ids)  # refreshes the same instances
        return records

    # READ

    @db_exceptions("retrieving record by ID")
    async def get_by_id(self, session: AsyncSession, record_id) -> ModelT | None:
        return await session.get(self.model, record_id)

    @db_exceptions("retrieving records by IDs")
    async def get_many_by_ids(self, session: AsyncSession, record_ids: Sequence) -> list[ModelT]:
        if not record_ids:
            return []
        stmt = select(self.model).where(self._column("id").in_(record_ids))
        return list((await session.execute(stmt)).scalars().all())

    @db_exceptions("retrieving record by fields")
    async def get_by_fields(self, session: AsyncSession, field_filters: Mapping[str, Any]) -> ModelT | None:
        stmt = self._select(self._where(field_filters), limit=1)
        return (await session.execute(stmt)).scalars().first()

    async def get_by_field(self, session: AsyncSession, field_name: str, field_value) -> ModelT | None:
        return await self.get_by_fields(session, {field_name: field_value})

    @db_exceptions("retrieving records by fields")
    async def get_many_by_fields(
        self,
        session: AsyncSession,
        field_filters: Mapping[str, Any],
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ) -> list[ModelT]:
        stmt = self._select(self._where(field_filters), limit, offset, order_by, order_direction)
        return list((await session.execute(stmt)).scalars().all())

    async def get_many_by_field(
        self,
        session: AsyncSession,
        field_name: str,
        field_value,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ) -> list[ModelT]:
        return await self.get_many_by_fields(
            session, {field_name: field_value}, limit, offset, order_by, order_direction
        )

    # UPDATE

    async def _update_one(
        self, session: AsyncSession, record: ModelT | None, update_data, not_found: str, commit: bool
    ) -> ModelT:
        if record is None:
            raise SqlNoResultException(not_found)
        self._apply(record, update_data)
        await self._save(session, commit)
        await session.refresh(record)
        return record

    @db_exceptions("updating record")
    async def update(self, session: AsyncSession, record_id, update_data: Mapping[str, Any], *, commit: bool = True) -> ModelT:
        record = await self.get_by_id(session, record_id)
        return await self._update_one(
            session, record, update_data, f"Record with ID {record_id} not found.", commit
        )

    @db_exceptions("updating record by field")
    async def update_by_field(
        self, session: AsyncSession, field_name: str, field_value, update_data: Mapping[str, Any], *, commit: bool = True
    ) -> ModelT:
        record = await self.get_by_field(session, field_name, field_value)
        return await self._update_one(
            session, record, update_data,
            f"Record with {field_name}={field_value} not found.", commit,
        )

    async def _update_where(
        self, session: AsyncSession, where: Sequence, update_data, not_found: str, commit: bool
    ) -> list[ModelT]:
        """Single UPDATE statement for all matching rows (no per-row loop)."""
        if not update_data:
            raise SqlException("update_data must not be empty")
        for key in update_data:
            self._column(key)

        pk = self._column("id")
        # Resolve matching IDs first so the update/reload still work when the
        # update changes the very column used in the filter.
        ids = (await session.execute(select(pk).where(*where))).scalars().all()
        if not ids:
            raise SqlNoResultException(not_found)

        await session.execute(update(self.model).where(pk.in_(ids)).values(**update_data))
        await self._save(session, commit)
        return await self._reload(session, ids)

    @db_exceptions("updating records")
    async def update_many(
        self, session: AsyncSession, record_ids: Sequence, update_data: Mapping[str, Any], *, commit: bool = True
    ) -> list[ModelT]:
        where = [self._column("id").in_(record_ids)]
        return await self._update_where(
            session, where, update_data, f"No records found with IDs {list(record_ids)}.", commit
        )

    @db_exceptions("updating records by field")
    async def update_many_by_field(
        self, session: AsyncSession, field_name: str, field_value, update_data: Mapping[str, Any], *, commit: bool = True
    ) -> list[ModelT]:
        where = self._where({field_name: field_value})
        return await self._update_where(
            session, where, update_data, f"No records found with {field_name}={field_value}.", commit
        )

    # DELETE
    # Uses session.delete() (not a bulk DELETE) so ORM-level cascades still run.

    async def _delete_records(
        self, session: AsyncSession, records: Sequence[ModelT], commit: bool
    ) -> None:
        for record in records:
            await session.delete(record)
        await self._save(session, commit)

    @db_exceptions("deleting record")
    async def delete(self, session: AsyncSession, record_id, *, commit: bool = True) -> ModelT:
        record = await self.get_by_id(session, record_id)
        if record is None:
            raise SqlNoResultException(f"Record with ID {record_id} not found.")
        await self._delete_records(session, [record], commit)
        return record

    @db_exceptions("deleting record by field")
    async def delete_by_field(self, session: AsyncSession, field_name: str, field_value, *, commit: bool = True) -> ModelT:
        record = await self.get_by_field(session, field_name, field_value)
        if record is None:
            raise SqlNoResultException(f"Record with {field_name}={field_value} not found.")
        await self._delete_records(session, [record], commit)
        return record

    @db_exceptions("deleting records")
    async def delete_many(self, session: AsyncSession, record_ids: Sequence, *, commit: bool = True) -> list[ModelT]:
        records = await self.get_many_by_ids(session, record_ids)
        if not records:
            raise SqlNoResultException(f"No records found with IDs {list(record_ids)}.")
        await self._delete_records(session, records, commit)
        return records

    @db_exceptions("deleting records by field")
    async def delete_many_by_field(
        self, session: AsyncSession, field_name: str, field_value, *, commit: bool = True
    ) -> list[ModelT]:
        records = await self.get_many_by_field(session, field_name, field_value)
        if not records:
            raise SqlNoResultException(f"No records found with {field_name}={field_value}.")
        await self._delete_records(session, records, commit)
        return records

    async def raw_query(self, session: AsyncSession, query: str, params: dict = None) -> list[Mapping[str, Any]]:
        """Execute a raw SQL query. Use with caution."""
        records = await session.execute(text(query), params)
        if not records:
            return []
        return [dict(row) for row in records.fetchall()]