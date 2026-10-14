import contextlib
from contextvars import ContextVar
from typing import Any, AsyncGenerator
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseSessionManager:
    def __init__(
        self, host: str, base: DeclarativeBase, engine_kwargs: dict[str, Any] = {}
    ):
        self._engine = create_async_engine(host, **engine_kwargs)
        self._sessionmaker = async_sessionmaker(autocommit=False, bind=self._engine)
        self._base = base
        self.db_context: ContextVar[AsyncSession] = ContextVar("db_session")

    async def close(self):
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        await self._engine.dispose()

        self._engine = None
        self._sessionmaker = None

    async def create_all(self) -> None:
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")

        async with self._engine.begin() as connection:
            await connection.run_sync(self._base.metadata.create_all)

    @contextlib.asynccontextmanager
    async def begin(self) -> AsyncGenerator[AsyncSession, None]:
        if self._sessionmaker is None:
            raise Exception("DatabaseSessionManager is not initialized")

        session = self._sessionmaker()
        token = self.db_context.set(session)
        try:
            async with session.begin():
                yield session
        finally:
            await session.close()
            self.db_context.reset(token)

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if self._sessionmaker is None:
            raise Exception("DatabaseSessionManager is not initialized")

        session = self._sessionmaker()
        token = self.db_context.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            self.db_context.reset(token)