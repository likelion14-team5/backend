from fastapi import APIRouter

from app.api.v1.meetings import router as meetings_router

api_router = APIRouter()
api_router.include_router(meetings_router)
