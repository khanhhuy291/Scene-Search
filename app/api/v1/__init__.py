"""Version 1 API router."""

from fastapi import APIRouter

from api.routes import router as legacy_router
from api.v1.ingestion import router as ingestion_router
from api.v1.search import router as search_router

api_router = APIRouter()
api_router.include_router(ingestion_router)
api_router.include_router(search_router)
api_router.include_router(legacy_router)

__all__ = ["api_router"]
