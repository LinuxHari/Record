from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from record.dependencies import get_settings
from record.__init__ import lifespan

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().app_url],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)