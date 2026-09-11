"""Version 1 API router."""

from fastapi import APIRouter

from api.v1.admin import router as admin_router
from api.v1.auth import router as auth_router
from api.v1.chat import router as chat_router
from api.v1.datasets import router as datasets_router
from api.v1.feedback import router as feedback_router
from api.v1.ingestion import router as ingestion_router
from api.v1.media import router as media_router
from api.v1.search import router as search_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(chat_router)
api_router.include_router(datasets_router)
api_router.include_router(feedback_router)
api_router.include_router(ingestion_router)
api_router.include_router(search_router)
api_router.include_router(media_router)

__all__ = ["api_router"]
