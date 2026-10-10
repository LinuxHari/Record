from functools import wraps

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


def db_exceptions(action: str):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, session: AsyncSession, **kwargs):
            print("Action:", action)
            try:
                return await fn(self, session, **kwargs)
            except SQLAlchemyError:
                await session.rollback()
                raise

        return wrapper

    return decorator
