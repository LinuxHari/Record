from fastapi import APIRouter

router = APIRouter(prefix="/ai", tags=["AI"])

@router.post("/chat/{chat_id}")
def chat(chat_id: str):
    return {"message": f"Chat endpoint for chat {chat_id}"}