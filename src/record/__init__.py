import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from record.db.sql.postgres.session import pg_sessionmanager
from record.db.cache.redis.cache_service import cache_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Application startup started")
    try:
        await pg_sessionmanager.create_all()
        logger.info("Database schema initialized")
        await cache_service.connect()
        logger.info("Application startup completed")
        yield
    except Exception:
        logger.exception("Application lifespan failed")
        raise
    finally:
        logger.info("Application shutdown started")
        if pg_sessionmanager._engine is not None:
            await pg_sessionmanager.close()

        if cache_service._pool is not None:
            await cache_service.disconnect()
        logger.info("Application shutdown completed")