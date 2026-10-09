from contextlib import asynccontextmanager
from fastapi import FastAPI
from record.db.pg import pg_sessionmanager

@asynccontextmanager
async def lifespan(_: FastAPI):

    try:
        await pg_sessionmanager.create_all()
        yield
    finally:
        if pg_sessionmanager._engine is not None:
            await pg_sessionmanager.close()