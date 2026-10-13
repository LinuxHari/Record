from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from record.dependencies import get_settings
from record.__init__ import lifespan
from record.app.assets.router import router as assets_router
from record.app.auth.router import router as auth_router
from record.app.ai.router import router as ai_router
from record.exceptions.exception_registry import CONSTRAINT_EXCEPTIONS
from record.handlers.exception_handler import register_exception_handlers
from record.handlers.response_handler import GlobalResponseHandler

# from fastapi import Depends
# from record.db.sql.postgres.session import get_pg_session
# from record.app.container import user_repository
# from record.app.user.models import User

# from record.exceptions.http_excpetions import NotFoundException

app = FastAPI(lifespan=lifespan)

register_exception_handlers(app, constraint_exceptions=CONSTRAINT_EXCEPTIONS)
app.router.route_class = GlobalResponseHandler

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().app_url],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(assets_router)
app.include_router(auth_router)
app.include_router(ai_router)

# @app.get("/", dependencies=[Depends(get_pg_session)])
# async def get_users():
#     records = await user_repository.find_by_email(email="hari@gmail.com")
#     if not records:
#         raise NotFoundException("User not found")
#     return records

# @app.post("/", dependencies=[Depends(get_pg_session)])
# async def create_user():
#     return await user_repository.create(User(username="Hariharan1", email="hari@gmail.com", password="HariHari"))


# @app.put("/")
# async def update_user(_: AsyncSession = Depends(get_pg_session)):
#     result = await user_repository.update(
#         {"email": "hari123@gmail.com"},
#         where=(User.email == "hari@gmail.com",),
#     )
#     if result is None:
#         raise NotFoundException("User not found")
#     return result

# @app.delete("/")
# async def delete_user(_: AsyncSession = Depends(get_pg_session)):
#     await user_repository.delete_by_field(where={"field": User.email, "value": "hari@gmail.com"})
#     return {"success": True}