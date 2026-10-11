import operator

from typing import Any, Generic, Mapping, Sequence, TypedDict, TypeVar
from sqlalchemy import inspect as sa_inspect, text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import UnmappedColumnError
from sqlalchemy.exc import NoResultFound

from .exceptions import db_exceptions

ModelT = TypeVar("ModelT")

class FieldFilter(TypedDict, total=False):
    """{"field": "email", "value": "a@b.com", "op": "eq"}  (op defaults to "eq")"""
    field: str
    value: Any
    op: str

def _eq(col, val):
    return col.is_(None) if val is None else col == val

def _ne(col, val):
    return col.is_not(None) if val is None else col != val

_OPERATORS = {
    "eq": _eq,
    "ne": _ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "in": lambda col, val: col.in_(val),
    "not_in": lambda col, val: col.not_in(val),
    "like": lambda col, val: col.like(val),
    "ilike": lambda col, val: col.ilike(val),
    "is_null": lambda col, val: col.is_(None) if val else col.is_not(None),
}

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
            raise UnmappedColumnError(
                f"Unknown value '{name}'"
            ) from None

    def _entities(self, columns: Sequence | None = None) -> tuple:
        """Resolve `columns` (names or column objects) into what select()/returning() take.
        No columns -> the full model entity (existing behaviour)."""
        if not columns:
            return (self.model,)
        return tuple(self._column(col) if isinstance(col, str) else col for col in columns)

    @staticmethod
    def _all(result, columns: Sequence | None) -> list:
        """Model instances when no columns, Row objects when columns are given."""
        return list(result.all() if columns else result.scalars().all())

    @staticmethod
    def _first(result, columns: Sequence | None):
        return result.first() if columns else result.scalars().first()

    def _clause(self, field_filter: FieldFilter):
        if not isinstance(field_filter, Mapping):
            raise ValueError(f"Filter must be a dict, got {type(field_filter).__name__}")
        unknown = set(field_filter) - {"field", "value", "op"}
        if unknown:
            raise ValueError(f"Unknown filter keys: {sorted(unknown)}")
        if "field" not in field_filter:
            raise ValueError("Filter is missing required key 'field'")

        op = field_filter.get("op", "eq")
        try:
            build = _OPERATORS[op]
        except KeyError:
            raise ValueError(
                f"Invalid op '{op}'. Supported: {sorted(_OPERATORS)}"
            ) from None
        if "value" not in field_filter and op != "is_null":
            raise ValueError(f"Filter on '{field_filter['field']}' is missing 'value'")

        col = self._column(field_filter["field"])
        return build(col, field_filter.get("value"))

    def _where(self, field_filters: Sequence[FieldFilter] | FieldFilter) -> list:
        if isinstance(field_filters, Mapping):  # allow a single filter dict
            field_filters = [field_filters]
        return [self._clause(filter) for filter in field_filters]

    def _select(
        self,
        *,
        where: Sequence,
        columns: Sequence | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ):
        if order_direction not in ("asc", "desc"):
            raise ValueError(f"Invalid order_direction '{order_direction}'")
        stmt = select(*self._entities(columns)).where(*where)
        if order_by:
            col = self._column(order_by)
            stmt = stmt.order_by(col.desc() if order_direction == "desc" else col.asc())
        return stmt.limit(limit).offset(offset)

    @staticmethod
    async def _save(session: AsyncSession, *, commit: bool) -> None:
        if commit:
            await session.commit()
        else:
            await session.flush()

    async def _reload(self, session: AsyncSession, *, ids: Sequence) -> list[ModelT]:
        stmt = (
            select(self.model)
            .where(self._column("id").in_(ids))
            .execution_options(populate_existing=True)
        )
        return list((await session.execute(stmt)).scalars().all())

    def _apply(self, record: ModelT, data: Mapping[str, Any]) -> None:
        if not data:
            raise ValueError("update_data must not be empty")
        for key in data:  # validate everything before touching the record
            self._column(key)
        for key, value in data.items():
            setattr(record, key, value)

    @db_exceptions("creating record")
    async def create(self, session: AsyncSession, *, model_data: ModelT, commit: bool = True) -> ModelT:
        session.add(model_data)
        await self._save(session, commit=commit)
        await session.refresh(model_data)
        return model_data

    @db_exceptions("creating records")
    async def create_many(
        self, session: AsyncSession, *, model_data_list: list[ModelT], commit: bool = True
    ) -> list[ModelT]:
        records = [self.model(**data) for data in model_data_list]
        if not records:
            return []
        session.add_all(records)
        await session.flush()
        ids = [r.id for r in records]
        await self._save(session, commit=commit)
        await self._reload(session, ids=ids)
        return records

    @db_exceptions("retrieving record by ID")
    async def get_by_id(
        self, session: AsyncSession, *, record_id, columns: Sequence | None = None
    ):
        if not columns:
            return await session.get(self.model, record_id)
        stmt = select(*self._entities(columns)).where(self._column("id") == record_id)
        return (await session.execute(stmt)).first()

    @db_exceptions("retrieving records by IDs")
    async def get_many_by_ids(self, session: AsyncSession, *, record_ids: Sequence, columns: Sequence | None = None) -> list[ModelT]:
        if not record_ids:
            return []
        stmt = select(*self._entities(columns)).where(self._column("id").in_(record_ids))
        return self._all(await session.execute(stmt), columns)

    @db_exceptions("retrieving record by fields")
    async def get_by_fields(
        self, session: AsyncSession, *, field_filters: Sequence[FieldFilter], columns: Sequence | None = None
    ) -> ModelT | None:
        for field in field_filters:
            if field["field"] not in self._columns:
                raise UnmappedColumnError(f"Unknown field {field['field']}")

        stmt = self._select(where=self._where(field_filters), columns=columns, limit=1)
        return self._first(await session.execute(stmt), columns)

    @db_exceptions("retrieving record by fields")
    async def get_by_field(self, session: AsyncSession, *, field_filter: FieldFilter, columns: Sequence | None = None) -> ModelT | None:
        return await self.get_by_fields(session, field_filters=[field_filter], columns=columns)

    @db_exceptions("retrieving records by fields")
    async def get_many_by_fields(
        self,
        session: AsyncSession,
        *,
        field_filters: Sequence[FieldFilter],
        columns: Sequence | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ) -> list[ModelT]:
        stmt = self._select(
            where=self._where(field_filters),
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_direction=order_direction,
        )
        return self._all(await session.execute(stmt), columns)

    async def get_many_by_field(
        self,
        session: AsyncSession,
        *,
        field_filter: FieldFilter,
        columns: Sequence | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ) -> list[ModelT]:
        return await self.get_many_by_fields(
            session,
            field_filters=[field_filter],
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_direction=order_direction,
        )

    async def _update_returning(
        self,
        session: AsyncSession,
        *,
        where: Sequence,
        update_data: Mapping[str, Any],
        columns: Sequence,
        commit: bool,
        single: bool = False,
    ) -> list:
        """One UPDATE ... RETURNING <columns> then commit.
        Replaces select + update + commit + refresh with a single statement + commit."""
        if not update_data:
            raise ValueError("update_data must not be empty")
        for key in update_data:
            self._column(key)

        if single:  # same semantics as get_by_field(): only the first match is updated
            pk = self._column("id")
            where = [pk == select(pk).where(*where).limit(1).scalar_subquery()]

        stmt = (
            update(self.model)
            .where(*where)
            .values(**update_data)
            .returning(*self._entities(columns))
        )
        rows = self._all(await session.execute(stmt), columns)
        if not rows:
            raise NoResultFound(f"No {self.model.__name__.lower()} found.")
        await self._save(session, commit=commit)
        return rows

    async def _update_one(
        self,
        session: AsyncSession,
        *,
        record: ModelT | None,
        update_data: Mapping[str, Any],
        commit: bool,
    ) -> ModelT:
        if record is None:
            raise NoResultFound(f"No {self.model.__name__.lower()} found.")
        self._apply(record, update_data)
        await self._save(session, commit=commit)
        await session.refresh(record)
        return record

    @db_exceptions("updating record")
    async def update(
        self,
        session: AsyncSession,
        *,
        record_id,
        update_data: Mapping[str, Any],
        columns: Sequence | None = None,
        commit: bool = True,
    ):
        if columns:  # fast path: single UPDATE ... RETURNING columns, then commit
            rows = await self._update_returning(
                session,
                where=[self._column("id") == record_id],
                update_data=update_data,
                columns=columns,
                commit=commit,
            )
            return rows[0]
        record = await self.get_by_id(session, record_id=record_id)
        return await self._update_one(
            session,
            record=record,
            update_data=update_data,
            commit=commit,
        )

    @db_exceptions("updating record by field")
    async def update_by_field(
        self,
        session: AsyncSession,
        *,
        field_filter: FieldFilter,
        update_data: Mapping[str, Any],
        columns: Sequence | None = None,
        commit: bool = True,
    ):
        if columns:
            rows = await self._update_returning(
                session,
                where=self._where([field_filter]),
                update_data=update_data,
                columns=columns,
                commit=commit,
                single=True,
            )
            return rows[0]
        record = await self.get_by_field(session, field_filter=field_filter)
        return await self._update_one(
            session,
            record=record,
            update_data=update_data,
            commit=commit,
        )

    async def _update_where(
        self,
        session: AsyncSession,
        *,
        where: Sequence,
        update_data: Mapping[str, Any],
        commit: bool,
        columns: Sequence | None = None,
    ) -> list[ModelT]:
        """Single UPDATE statement for all matching rows (no per-row loop)."""
        if columns:  # only the requested columns come back; no id pre-select, no reload
            return await self._update_returning(
                session,
                where=where,
                update_data=update_data,
                columns=columns,
                commit=commit,
            )

        if not update_data:
            raise ValueError("update_data must not be empty")
        for key in update_data:
            self._column(key)

        pk = self._column("id")
        # update changes the very column used in the filter.
        ids = (await session.execute(select(pk).where(*where))).scalars().all()
        if not ids:
            raise NoResultFound(f"No {self.model.__name__.lower()} found.")

        await session.execute(update(self.model).where(pk.in_(ids)).values(**update_data))
        await self._save(session, commit=commit)
        return await self._reload(session, ids=ids)

    @db_exceptions("updating records")
    async def update_many(
        self,
        session: AsyncSession,
        *,
        record_ids: Sequence,
        update_data: Mapping[str, Any],
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> list[ModelT]:
        where = [self._column("id").in_(record_ids)]
        return await self._update_where(
            session,
            where=where,
            update_data=update_data,
            columns=columns,
            commit=commit,
        )

    @db_exceptions("updating records by fields")
    async def update_many_by_fields(
        self,
        session: AsyncSession,
        *,
        field_filters: Sequence[FieldFilter],
        update_data: Mapping[str, Any],
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> list[ModelT]:
        return await self._update_where(
            session,
            where=self._where(field_filters),
            update_data=update_data,
            columns=columns,
            commit=commit,
        )

    @db_exceptions("updating records by field")
    async def update_many_by_field(
        self,
        session: AsyncSession,
        *,
        field_filter: FieldFilter,
        update_data: Mapping[str, Any],
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> list[ModelT]:
        return await self._update_where(
            session,
            where=self._where([field_filter]),
            update_data=update_data,
            columns=columns,
            commit=commit,
        )

    async def _delete_records(
        self, session: AsyncSession, *, records: Sequence[ModelT], commit: bool
    ) -> None:
        for record in records:
            await session.delete(record)
        await self._save(session, commit=commit)

    @db_exceptions("deleting record")
    async def delete(self, session: AsyncSession, *, record_id, commit: bool = True) -> ModelT:
        record = await self.get_by_id(session, record_id=record_id)
        if record is None:
            raise NoResultFound(f"Record with ID {record_id} not found.")
        await self._delete_records(session, records=[record], commit=commit)
        return record

    @db_exceptions("deleting record by fields")
    async def delete_by_fields(
        self, session: AsyncSession, *, field_filters: FieldFilter, commit: bool = True
    ) -> ModelT:
        record = await self.get_by_fields(session, field_filters=field_filters)
        if record:
            await self._delete_records(session, records=[record], commit=commit)
        return record

    @db_exceptions("deleting record by field")
    async def delete_by_field(
        self, session: AsyncSession, *, field_filter: FieldFilter, commit: bool = True
    ) -> ModelT:
        record = await self.get_by_field(session, field_filter=field_filter)
        if record:
            await self._delete_records(session, records=[record], commit=commit)
        return record

    @db_exceptions("deleting records")
    async def delete_many(
        self, session: AsyncSession, *, record_ids: Sequence, commit: bool = True
    ) -> list[ModelT]:
        records = await self.get_many_by_ids(session, record_ids=record_ids)
        if records:
            await self._delete_records(session, records=records, commit=commit)
        return records

    @db_exceptions("deleting records by fields")
    async def delete_many_by_fields(
        self, session: AsyncSession, *, field_filters: Sequence[FieldFilter], commit: bool = True
    ) -> list[ModelT]:
        records = await self.get_many_by_fields(session, field_filters=field_filters)
        if records:
            await self._delete_records(session, records=records, commit=commit)
        return records

    @db_exceptions("deleting records by field")
    async def delete_many_by_field(
        self, session: AsyncSession, *, field_filter: FieldFilter, commit: bool = True
    ) -> list[ModelT]:
        records = await self.get_many_by_field(session, field_filter=field_filter)
        if records:
            await self._delete_records(session, records=records, commit=commit)
        return records

    async def raw_query(
        self, session: AsyncSession, *, query: str, params: dict | None = None
    ) -> list[Mapping[str, Any]]:
        """Execute a raw SQL query. Use with caution."""
        result = await session.execute(text(query), params)
        return [dict(row) for row in result.mappings().all()]