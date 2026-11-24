"""Best-effort catalog invalidation after an index mutation."""

from loguru import logger

from infrastructure.redis import get_redis_client

CATALOG_GENERATION_KEY = "scenesearch:search-catalog-generation"


async def invalidate_catalog() -> None:
    try:
        await get_redis_client().incr(CATALOG_GENERATION_KEY)
    except Exception:
        # Publication has already succeeded. TTL is the existing recovery path.
        logger.exception("Could not signal search catalog reload; TTL fallback remains active")
