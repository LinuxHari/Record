from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from record.dependencies import get_settings 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)