from fastapi import APIRouter, Depends
from record.db.sql.postgres.session import get_pg_session

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login")
def login():
    return {"message": "User logged in successfully"}

@router.post("/register", dependencies=[Depends(get_pg_session)])
async def signup():
    return None

@router.post("/logout")
def logout():
    return {"message": "User logged out successfully"}

@router.get("/refresh")
def refresh_token():
    return {"message": "Token refreshed successfully"}