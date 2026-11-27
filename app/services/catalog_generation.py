"""Best-effort catalog invalidation after an index mutation."""

from loguru import logger

from infrastructure.redis import get_redis_client

CATALOG_GENERATION_KEY = "scenesearch:search-catalog-generation"


async def catalog_revision() -> int | None:
    try:
        return int(await get_redis_client().get(CATALOG_GENERATION_KEY) or 0)
    except Exception:
        logger.debug("Catalog revision unavailable; using the existing TTL fallback")
        return None


async def invalidate_catalog() -> None:
    try:
        await get_redis_client().incr(CATALOG_GENERATION_KEY)
    except Exception:
        # Publication has already succeeded. TTL is the existing recovery path.
        logger.exception("Could not signal search catalog reload; TTL fallback remains active")
