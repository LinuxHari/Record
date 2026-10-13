from functools import wraps

from sqlalchemy.exc import SQLAlchemyError


def db_exceptions(action: str):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, *args, **kwargs):
            print("Action:", action)
            try:
                return await fn(self, *args, **kwargs)
            except SQLAlchemyError as e:
                print(e)
                await self.session.rollback()
                raise

        return wrapper

    return decorator
