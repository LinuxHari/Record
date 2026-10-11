import operator

from typing import Any, Generic, Mapping, Sequence, TypedDict, TypeVar
from sqlalchemy import inspect as sa_inspect, text, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.exc import UnmappedColumnError
from sqlalchemy.exc import NoResultFound

from .exceptions import db_exceptions

ModelT = TypeVar("ModelT")
Row = dict[str, Any]


class WhereClause(TypedDict, total=False):
    """A where clause using a mapped field name or model attribute."""
    field: str | InstrumentedAttribute[Any]
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
        mapper = sa_inspect(model)
        self._columns = {
            attr.key: getattr(model, attr.key) for attr in mapper.column_attrs
        }
        pk_cols = mapper.primary_key
        if len(pk_cols) != 1:
            raise ValueError(
                f"{model.__name__} must have a single-column primary key"
            )
        self._pk_name = mapper.get_property_by_column(pk_cols[0]).key
        self._pk = self._columns[self._pk_name]

    # ---------- helpers ----------

    def _column(self, name: str | InstrumentedAttribute[Any]):
        if isinstance(name, InstrumentedAttribute):
            if name.class_ is not self.model:
                raise UnmappedColumnError(f"Unknown value '{name}'")
            name = name.key
        try:
            return self._columns[name]
        except KeyError:
            raise UnmappedColumnError(f"Unknown value '{name}'") from None

    def _validate_values(self, values: Mapping[str, Any], label: str = "update_data") -> None:
        """Non-empty and every key is a mapped column. Validates before anything is touched."""
        if not values:
            raise ValueError(f"{label} must not be empty")
        for key in values:
            self._column(key)

    def _not_found(self) -> NoResultFound:
        return NoResultFound(f"No {self.model.__name__.lower()} found.")

    def _entities(self, columns: Sequence | None = None) -> tuple:
        """Resolve `columns` (names or column objects) into what select()/returning() take.
        No columns -> the full model entity."""
        if not columns:
            return (self.model,)
        return tuple(self._column(col) if isinstance(col, str) else col for col in columns)

    @staticmethod
    def _all(result, columns: Sequence | None) -> list:
        """Model instances when no columns, dictionaries when columns are given."""
        if columns:
            return [dict(row) for row in result.mappings().all()]
        return list(result.scalars().all())

    @staticmethod
    def _first(result, columns: Sequence | None):
        if columns:
            row = result.mappings().first()
            return dict(row) if row is not None else None
        return result.scalars().first()

    def _clause(self, where: WhereClause):
        if not isinstance(where, Mapping):
            raise ValueError(f"Where clause must be a dict, got {type(where).__name__}")
        unknown = set(where) - {"field", "value", "op"}
        if unknown:
            raise ValueError(f"Unknown where keys: {sorted(unknown)}")
        if "field" not in where:
            raise ValueError("Where clause is missing required key 'field'")

        op = where.get("op", "eq")
        try:
            build = _OPERATORS[op]
        except KeyError:
            raise ValueError(
                f"Invalid op '{op}'. Supported: {sorted(_OPERATORS)}"
            ) from None
        if "value" not in where and op != "is_null":
            raise ValueError(f"Where clause on '{where['field']}' is missing 'value'")

        return build(self._column(where["field"]), where.get("value"))

    def _build_where(self, where: Sequence[WhereClause] | WhereClause) -> list:
        if isinstance(where, Mapping):
            where = [where]
        return [self._clause(clause) for clause in where]

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
        elif limit is not None or offset is not None:
            stmt = stmt.order_by(self._pk)  # stable pagination
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
            .where(self._pk.in_(ids))
            .execution_options(populate_existing=True)
        )
        return list((await session.execute(stmt)).scalars().all())

    def _apply(self, record: ModelT, data: Mapping[str, Any]) -> None:
        self._validate_values(data)
        for key, value in data.items():
            setattr(record, key, value)

    # ---------- create ----------

    @db_exceptions("creating record")
    async def create(self, session: AsyncSession, record: ModelT, *, commit: bool = True) -> ModelT:
        session.add(record)
        await self._save(session, commit=commit)
        await session.refresh(record)
        return record

    @db_exceptions("creating records")
    async def create_many(
        self, session: AsyncSession, records: list[ModelT], *, commit: bool = True
    ) -> list[ModelT]:
        if not records:
            return []
        session.add_all(records)
        await session.flush()
        ids = [getattr(r, self._pk_name) for r in records]
        await self._save(session, commit=commit)
        await self._reload(session, ids=ids)
        return records

    # ---------- upsert ----------

    def _record_values(self, record: ModelT) -> dict[str, Any]:
        state = sa_inspect(record)
        return {key: value for key, value in state.dict.items() if key in self._columns}

    async def _upsert_rows(
        self,
        session: AsyncSession,
        *,
        rows: Sequence[Mapping[str, Any]],
        conflict_fields: Sequence[str | InstrumentedAttribute[Any]],
    ) -> list[ModelT]:
        """Single INSERT ... ON CONFLICT DO UPDATE ... RETURNING (race-free).
        All rows must have the same keys, and conflict keys must be unique within the batch
        (Postgres can't update the same row twice in one statement)."""
        if not rows:
            return []
        keys = set(rows[0])
        self._validate_values(rows[0], "record data")
        if any(set(row) != keys for row in rows):
            raise ValueError("all records in a batch must have the same fields")
        if not conflict_fields:
            raise ValueError("conflict_fields must not be empty")

        conflict_cols = [self._column(f) for f in conflict_fields]
        conflict_names = [c.key for c in conflict_cols]
        if len(set(conflict_names)) != len(conflict_names):
            raise ValueError("conflict_fields must not contain duplicates")
        if not keys.issuperset(conflict_names):
            raise ValueError("record data must include every conflict field")
        # NULLs never conflict in a unique index, so this would silently insert duplicates
        if any(row[name] is None for row in rows for name in conflict_names):
            raise ValueError("conflict fields must not be None")

        update_names = [k for k in rows[0] if k not in conflict_names and k != self._pk_name]
        stmt = pg_insert(self.model).values([dict(r) for r in rows])
        # If there's nothing to update, no-op "update" so the existing row is still returned.
        set_ = {name: stmt.excluded[name] for name in (update_names or conflict_names)}
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols, set_=set_
        ).returning(self.model)

        result = await session.execute(stmt, execution_options={"populate_existing": True})
        return list(result.scalars().all())

    @db_exceptions("upserting record")
    async def upsert(
        self,
        session: AsyncSession,
        record: ModelT,
        *,
        conflict_fields: Sequence[str | InstrumentedAttribute[Any]],
        commit: bool = True,
    ) -> ModelT:
        rows = await self._upsert_rows(
            session,
            rows=[self._record_values(record)],
            conflict_fields=conflict_fields,
        )
        await self._save(session, commit=commit)
        return rows[0]

    @db_exceptions("upserting records")
    async def upsert_many(
        self,
        session: AsyncSession,
        *,
        model_data_list: list[Mapping[str, Any]],
        conflict_fields: Sequence[str | InstrumentedAttribute[Any]],
        commit: bool = True,
    ) -> list[ModelT]:
        """Returned order is not guaranteed to match input order."""
        records = await self._upsert_rows(
            session, rows=model_data_list, conflict_fields=conflict_fields
        )
        if records:
            await self._save(session, commit=commit)
        return records

    # ---------- read ----------

    @db_exceptions("retrieving record by ID")
    async def get_by_id(
        self, session: AsyncSession, *, record_id, columns: Sequence | None = None
    ) -> ModelT | Row | None:
        if not columns:
            return await session.get(self.model, record_id)
        stmt = select(*self._entities(columns)).where(self._pk == record_id)
        return self._first(await session.execute(stmt), columns)

    @db_exceptions("retrieving records by IDs")
    async def get_many_by_ids(
        self, session: AsyncSession, *, record_ids: Sequence, columns: Sequence | None = None
    ) -> list[ModelT] | list[Row]:
        if not record_ids:
            return []
        stmt = select(*self._entities(columns)).where(self._pk.in_(record_ids))
        return self._all(await session.execute(stmt), columns)

    @db_exceptions("retrieving record by fields")
    async def get_by_fields(
        self,
        session: AsyncSession,
        *,
        where: Sequence[WhereClause] | WhereClause,
        columns: Sequence | None = None,
    ) -> ModelT | Row | None:
        stmt = self._select(where=self._build_where(where), columns=columns, limit=1)
        return self._first(await session.execute(stmt), columns)

    async def get_by_field(
        self, session: AsyncSession, *, where: WhereClause, columns: Sequence | None = None
    ) -> ModelT | Row | None:
        return await self.get_by_fields(session, where=where, columns=columns)

    @db_exceptions("retrieving records by fields")
    async def get_many_by_fields(
        self,
        session: AsyncSession,
        *,
        where: Sequence[WhereClause] | WhereClause,
        columns: Sequence | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ) -> list[ModelT] | list[Row]:
        stmt = self._select(
            where=self._build_where(where),
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
        where: WhereClause,
        columns: Sequence | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_direction: str = "asc",
    ) -> list[ModelT] | list[Row]:
        return await self.get_many_by_fields(
            session,
            where=where,
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_direction=order_direction,
        )

    # ---------- update ----------

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
        """One UPDATE ... RETURNING <columns>, then commit/flush.
        single=True updates only one row (lowest id among matches).
        Raises NoResultFound if single and nothing matched; bulk returns []."""
        self._validate_values(update_data)

        if single:
            where = [
                self._pk == select(self._pk).where(*where).order_by(self._pk).limit(1).scalar_subquery()
            ]

        stmt = (
            update(self.model)
            .where(*where)
            .values(**update_data)
            .returning(*self._entities(columns))
        )
        rows = self._all(await session.execute(stmt), columns)
        if not rows:
            if single:
                raise self._not_found()
            return []
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
            raise self._not_found()
        self._apply(record, update_data)
        await self._save(session, commit=commit)
        await session.refresh(record)
        return record

    @db_exceptions("updating record")
    async def update(
        self,
        session: AsyncSession,
        update_data: Mapping[str, Any],
        *,
        record_id,
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> ModelT | Row:
        if columns:
            rows = await self._update_returning(
                session,
                where=[self._pk == record_id],
                update_data=update_data,
                columns=columns,
                commit=commit,
                single=True,
            )
            return rows[0]
        record = await self.get_by_id(session, record_id=record_id)
        return await self._update_one(
            session, record=record, update_data=update_data, commit=commit
        )

    @db_exceptions("updating record by field")
    async def update_by_field(
        self,
        session: AsyncSession,
        update_data: Mapping[str, Any],
        *,
        where: WhereClause,
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> ModelT | Row:
        if columns:
            rows = await self._update_returning(
                session,
                where=self._build_where(where),
                update_data=update_data,
                columns=columns,
                commit=commit,
                single=True,
            )
            return rows[0]
        record = await self.get_by_field(session, where=where)
        return await self._update_one(
            session, record=record, update_data=update_data, commit=commit
        )

    async def _update_where(
        self,
        session: AsyncSession,
        *,
        where: Sequence,
        update_data: Mapping[str, Any],
        commit: bool,
        columns: Sequence | None = None,
    ) -> list[ModelT] | list[Row]:
        """Single UPDATE statement for all matching rows (no per-row loop)."""
        if columns:
            return await self._update_returning(
                session,
                where=where,
                update_data=update_data,
                columns=columns,
                commit=commit,
            )

        self._validate_values(update_data)
        # RETURNING id captures exactly the rows changed, even if update_data
        # modifies a column used in the filter, and avoids a select/update gap.
        stmt = update(self.model).where(*where).values(**update_data).returning(self._pk)
        ids = list((await session.execute(stmt)).scalars().all())
        if not ids:
            return []
        await self._save(session, commit=commit)
        return await self._reload(session, ids=ids)

    @db_exceptions("updating records")
    async def update_many(
        self,
        session: AsyncSession,
        update_data: Mapping[str, Any],
        *,
        record_ids: Sequence,
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> list[ModelT] | list[Row]:
        if not record_ids:
            return []
        return await self._update_where(
            session,
            where=[self._pk.in_(record_ids)],
            update_data=update_data,
            columns=columns,
            commit=commit,
        )

    @db_exceptions("updating records by fields")
    async def update_many_by_fields(
        self,
        session: AsyncSession,
        update_data: Mapping[str, Any],
        *,
        where: Sequence[WhereClause] | WhereClause,
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> list[ModelT] | list[Row]:
        return await self._update_where(
            session,
            where=self._build_where(where),
            update_data=update_data,
            columns=columns,
            commit=commit,
        )

    async def update_many_by_field(
        self,
        session: AsyncSession,
        update_data: Mapping[str, Any],
        *,
        where: WhereClause,
        columns: Sequence | None = None,
        commit: bool = True,
    ) -> list[ModelT] | list[Row]:
        return await self.update_many_by_fields(
            session, update_data, where=where, columns=columns, commit=commit
        )

    # ---------- delete ----------

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
            raise self._not_found()
        await self._delete_records(session, records=[record], commit=commit)
        return record

    @db_exceptions("deleting record by fields")
    async def delete_by_fields(
        self, session: AsyncSession, *, where: Sequence[WhereClause] | WhereClause, commit: bool = True
    ) -> ModelT:
        record = await self.get_by_fields(session, where=where)
        if record is None:
            raise self._not_found()
        await self._delete_records(session, records=[record], commit=commit)
        return record

    async def delete_by_field(
        self, session: AsyncSession, *, where: WhereClause, commit: bool = True
    ) -> ModelT:
        return await self.delete_by_fields(session, where=where, commit=commit)

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
        self, session: AsyncSession, *, where: Sequence[WhereClause] | WhereClause, commit: bool = True
    ) -> list[ModelT]:
        records = await self.get_many_by_fields(session, where=where)
        if records:
            await self._delete_records(session, records=records, commit=commit)
        return records

    async def delete_many_by_field(
        self, session: AsyncSession, *, where: WhereClause, commit: bool = True
    ) -> list[ModelT]:
        return await self.delete_many_by_fields(session, where=where, commit=commit)

    # ---------- raw ----------

    @db_exceptions("executing raw query")
    async def raw_query(
        self, session: AsyncSession, *, query: str, params: dict | None = None
    ) -> list[Mapping[str, Any]]:
        """Execute a raw SQL query. Use with caution."""
        result = await session.execute(text(query), params)
        return [dict(row) for row in result.mappings().all()]