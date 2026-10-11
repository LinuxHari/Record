from functools import wraps

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


def db_exceptions(action: str):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, session: AsyncSession, *args, **kwargs):
            print("Action:", action)
            try:
                return await fn(self, session, *args, **kwargs)
            except SQLAlchemyError as e:
                print(e)
                await session.rollback()
                raise

        return wrapper

    return decorator
