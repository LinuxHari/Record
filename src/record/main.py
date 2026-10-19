from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from record.dependencies import get_settings
from record import lifespan
from record.logging import RequestLoggingMiddleware, setup_logging
from record.app.assets.router import router as assets_router
from record.app.auth.router import router as auth_router
from record.app.ai.router import router as ai_router
from record.exceptions.exception_registry import CONSTRAINT_EXCEPTIONS
from record.handlers.exception_handler import register_exception_handlers

setup_logging()

app = FastAPI(lifespan=lifespan)

register_exception_handlers(app, constraint_exceptions=CONSTRAINT_EXCEPTIONS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().app_url],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(assets_router)
app.include_router(auth_router)
app.include_router(ai_router)