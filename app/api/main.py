"""SceneSearch FastAPI application entry point."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text

from api.v1 import api_router
from core.config import get_settings
from core.logging import configure_logging
from infrastructure.minio import get_minio_storage
from infrastructure.postgres import close_postgres, get_engine
from infrastructure.qdrant import close_qdrant, init_qdrant_collections
from infrastructure.redis import check_redis_connection, close_redis


async def _check_postgres() -> None:
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _check_minio() -> None:
    await asyncio.to_thread(get_minio_storage().ensure_bucket)


async def _initialize_infrastructure() -> None:
    await _check_postgres()
    await check_redis_connection()
    await init_qdrant_collections()
    await _check_minio()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.app.log_level, json_logs=settings.app.env != "development")
    logger.info(
        "Starting {name} in {environment} mode",
        name=settings.app.name,
        environment=settings.app.env,
    )

    try:
        try:
            await _initialize_infrastructure()
            logger.info("Infrastructure readiness checks passed")
        except Exception:
            logger.exception("Infrastructure readiness checks failed")
            if settings.app.env in {"staging", "production"}:
                raise

        yield
    finally:
        results = await asyncio.gather(
            close_qdrant(),
            close_redis(),
            close_postgres(),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Infrastructure shutdown failed: {error}", error=result)
        logger.info("Application shutdown complete")


settings = get_settings()
app = FastAPI(
    title=settings.app.name,
    description="Multimodal scene indexing and semantic search API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app.env}


__all__ = ["app", "lifespan"]
