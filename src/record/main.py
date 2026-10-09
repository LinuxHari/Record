from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from record.dependencies import get_settings
from record.__init__ import lifespan
from record.assets.router import router as assets_router
from record.auth.router import router as auth_router
from record.ai.router import router as ai_router

app = FastAPI(lifespan=lifespan)

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