from fastapi import APIRouter

from app.api.v1.ai import router as ai_router
from app.api.v1.meetings import router as meetings_router

api_router = APIRouter()
api_router.include_router(meetings_router)
api_router.include_router(ai_router)
