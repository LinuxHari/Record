from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login")
def login():
    return {"message": "User logged in successfully"}

@router.post("/register")
def register():
    return {"message": "User registered successfully"}

@router.post("/logout")
def logout():
    return {"message": "User logged out successfully"}

@router.get("/refresh")
def refresh_token():
    return {"message": "Token refreshed successfully"}