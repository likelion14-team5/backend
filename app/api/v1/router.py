from fastapi import APIRouter

from app.api.v1.ai import router as ai_router
from app.api.v1.meetings import router as meetings_router
from app.api.v1.pre_speech import router as pre_speech_router
from app.api.v1.speech_feedback import router as speech_feedback_router

api_router = APIRouter()
api_router.include_router(meetings_router)
api_router.include_router(pre_speech_router)
api_router.include_router(speech_feedback_router)
api_router.include_router(ai_router)
