from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
)
from record.dependencies import get_settings
from record.db.sql.service import DatabaseSessionManager
from record.db.sql.conventions import metadata

class PGBase(AsyncAttrs, DeclarativeBase):
    metadata = metadata

pg_sessionmanager = DatabaseSessionManager(get_settings().db_url, PGBase, {"echo": True, "pool_size": 10, "max_overflow": 20, "future": True})

async def get_pg_session():
    async with pg_sessionmanager.session() as session:
        yield session