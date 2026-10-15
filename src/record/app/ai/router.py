from fastapi import APIRouter
from record.handlers.response_handler import GlobalResponseHandler

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
    route_class=GlobalResponseHandler,
)

@router.post("/chat/{chat_id}")
def chat(chat_id: str):
    return {"message": f"Chat endpoint for chat {chat_id}"}