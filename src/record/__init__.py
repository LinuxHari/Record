from contextlib import asynccontextmanager
from fastapi import FastAPI
from record.db.sql.postgres.session import pg_sessionmanager
from record.db.memory.redis.cache_service import cache_service

@asynccontextmanager
async def lifespan(_: FastAPI):

    try:
        await pg_sessionmanager.create_all()
        await cache_service.connect()
        yield
    finally:
        if pg_sessionmanager._engine is not None:
            await pg_sessionmanager.close()

        if cache_service._pool is not None:
            await cache_service.disconnect()