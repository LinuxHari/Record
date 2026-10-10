from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from record.dependencies import get_settings
from record.__init__ import lifespan
from record.assets.router import router as assets_router
from record.auth.router import router as auth_router
from record.ai.router import router as ai_router
from record.error_registry import CONSTRAINT_ERRORS
from record.exceptions import register_exception_handlers

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from record.db.sql.postgres.session import get_pg_session
from record.user.repository import user_repository

app = FastAPI(lifespan=lifespan)

register_exception_handlers(app, constraint_errors=CONSTRAINT_ERRORS)

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

@app.get("/")
async def get_users(db: AsyncSession = Depends(get_pg_session)): 
    records = await user_repository.get_by_field(db, field_filter={"field": "username", "value": "Hariharan"})
    return records

@app.post("/")
async def create_user(db: AsyncSession = Depends(get_pg_session)):
    await user_repository.create(db, model_data={"username":"Hariharan", "email":"test@gmail.com", "password": "hellohello"})
    return {"success": True} 

@app.put("/")
async def update_user(db: AsyncSession = Depends(get_pg_session)):
    await user_repository.update_by_field(db, update_data={"email": "test123@gmail.com"}, field_filter={"field": "email", "value": "tes@gmail.com"})
    return {"success": True} 

@app.delete("/")
async def delete_user(db: AsyncSession = Depends(get_pg_session)):
    await user_repository.delete_by_field(db, field_filter={"field": "email", "value": "test123@gmail.com"})
    return {"success": True}