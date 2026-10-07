from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import responses

app = FastAPI(responses=responses)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)