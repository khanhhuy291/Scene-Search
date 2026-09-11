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
from infrastructure.minio import get_derived_storage, get_minio_storage, get_raw_storage
from infrastructure.postgres import close_postgres, get_engine
from infrastructure.qdrant import close_qdrant, init_qdrant_collections
from infrastructure.redis import check_redis_connection, close_redis


async def _check_postgres() -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))
        try:
            from db.models import Base

            await connection.run_sync(Base.metadata.create_all)
            logger.info("Database schema verified/created successfully")
        except Exception as exc:
            logger.warning("Database schema auto-creation skipped: {}", exc)


async def _check_minio() -> None:
    # All three buckets, not just the default one. The raw/derived split is the
    # privacy mechanism (ADR-0003), so ingestion must never reach a state where
    # it has an original to store and nowhere separate to put it.
    stores = (get_minio_storage(), get_raw_storage(), get_derived_storage())

    def ensure_all_buckets() -> None:
        for storage in stores:
            storage.ensure_bucket()

    # The MinIO SDK is synchronous. Keep all three quick startup checks in one
    # worker-thread handoff instead of consuming a separate pool job per bucket.
    await asyncio.to_thread(ensure_all_buckets)


async def _initialize_infrastructure() -> None:
    try:
        await _check_postgres()
    except Exception as exc:
        logger.warning("Postgres check skipped/failed: {}", exc)
    try:
        await check_redis_connection()
    except Exception as exc:
        logger.warning("Redis check skipped/failed: {}", exc)
    try:
        await init_qdrant_collections()
    except Exception as exc:
        logger.warning("Qdrant check skipped/failed: {}", exc)
    try:
        await _check_minio()
    except Exception as exc:
        logger.warning("Storage bucket check skipped/failed: {}", exc)


async def _warm_search() -> None:
    """Load the keyframe catalog and query encoder ahead of the first search.

    Deliberately not awaited during startup. Together these take some seconds --
    reading every payload, then loading encoder weights -- and blocking startup on
    them would delay readiness checks and make a deploy look hung. Run in the
    background, the cost lands before a user types instead of inside their first
    query.
    """

    try:
        settings = get_settings()
        from infrastructure.qdrant import get_qdrant_client
        from search.catalog import get_catalog

        qdrant_client = get_qdrant_client()
        try:
            await get_catalog().ensure_loaded(qdrant_client)
            logger.info("Keyframe catalog warmup complete")
            from api.v1.media import precache_startup_thumbnails

            asyncio.create_task(precache_startup_thumbnails(limit=100))
        except Exception as exc:
            logger.warning("Catalog warmup skipped/failed: {}", exc)

        mode = settings.search.mode.lower()
        if mode == "qwen":
            from ml.encoder import get_qwen_encoder

            try:
                await asyncio.to_thread(get_qwen_encoder().encode_texts, ["warmup"])
            except Exception as exc:
                logger.warning("Qwen encoder warmup skipped: {}", exc)
        elif mode == "siglip":
            from ml.encoder import get_siglip_encoder

            try:
                await asyncio.to_thread(get_siglip_encoder().load)
            except Exception as exc:
                logger.warning("SigLIP encoder warmup skipped: {}", exc)
        else:  # hybrid or other modes
            from ml.encoder import get_qwen_encoder, get_siglip_encoder

            try:
                await asyncio.to_thread(get_siglip_encoder().load)
            except Exception as exc:
                logger.warning("SigLIP encoder warmup skipped: {}", exc)
            if settings.ml.qwen_embedding_url or "qwen" in settings.ml.encoder_name.lower():
                try:
                    await asyncio.to_thread(get_qwen_encoder().encode_texts, ["warmup"])
                except Exception as exc:
                    logger.debug("Qwen encoder warmup skipped: {}", exc)

        if settings.search.rerank_enabled:
            from ml.reranker import get_reranker

            try:
                await asyncio.to_thread(get_reranker().load)
            except Exception as exc:
                logger.warning("Reranker warmup skipped: {}", exc)

        logger.info("Search warmup complete")
    except asyncio.CancelledError:
        raise
    except Exception:
        # A cold search is slow, not broken. It will load on demand.
        logger.exception("Search warmup failed; the first search will pay the load cost")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.app.log_level, json_logs=settings.app.env != "development")
    logger.info(
        "Starting {name} in {environment} mode",
        name=settings.app.name,
        environment=settings.app.env,
    )

    warmup: asyncio.Task[None] | None = None
    try:
        try:
            await _initialize_infrastructure()
            logger.info("Infrastructure readiness checks complete")
        except Exception as exc:
            logger.warning("Infrastructure readiness checks encountered warnings: {}", exc)

        warmup = asyncio.create_task(_warm_search())

        yield
    finally:
        if warmup is not None and not warmup.done():
            warmup.cancel()
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
