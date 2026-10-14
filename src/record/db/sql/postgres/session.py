from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
)
from record.dependencies import get_settings
from record.db.sql.service import DatabaseSessionManager
from record.db.sql.conventions import metadata


class PGBase(AsyncAttrs, DeclarativeBase):
    metadata = metadata


pg_sessionmanager = DatabaseSessionManager(
    get_settings().db_url,
    PGBase,
    {"echo": True, "pool_size": 10, "max_overflow": 20, "future": True},
)


async def get_pg_session():
    async with pg_sessionmanager.session() as session:
        yield session


async def get_pg_transaction():
    async with pg_sessionmanager.begin() as transaction:
        yield transaction


def get_pg_context() -> AsyncSession:
    return pg_sessionmanager.db_context.get()
