"""Shared asynchronous Redis client and connection pool."""

from __future__ import annotations

from urllib.parse import quote

from redis.asyncio import ConnectionPool, Redis

from core.config import RedisSettings, get_settings

_pool: ConnectionPool | None = None
_client: Redis | None = None


def _redis_url(settings: RedisSettings) -> str:
    if settings.url:
        return settings.url
    password = settings.password.get_secret_value() if settings.password else None
    credentials = f":{quote(password, safe='')}@" if password else ""
    return f"redis://{credentials}{settings.host}:{settings.port}/{settings.db}"


def get_redis_pool() -> ConnectionPool:
    """Create and return the process-wide Redis connection pool."""

    global _pool
    if _pool is None:
        settings = get_settings().redis
        _pool = ConnectionPool.from_url(
            _redis_url(settings),
            max_connections=settings.max_connections,
            decode_responses=True,
            encoding="utf-8",
            socket_timeout=settings.socket_timeout,
            socket_connect_timeout=settings.socket_connect_timeout,
            health_check_interval=settings.health_check_interval,
        )
    return _pool


def get_redis_client() -> Redis:
    """Return a singleton async Redis client backed by the shared pool."""

    global _client
    if _client is None:
        _client = Redis(connection_pool=get_redis_pool())
    return _client


async def check_redis_connection() -> None:
    """Raise ``redis.exceptions.RedisError`` when Redis is unavailable."""

    if not await get_redis_client().ping():
        raise ConnectionError("Redis PING returned a false response")


async def close_redis() -> None:
    """Close the client and disconnect every pooled Redis connection."""

    global _client, _pool
    client, pool, _client, _pool = _client, _pool, None, None
    if client is not None:
        await client.aclose(close_connection_pool=False)
    if pool is not None:
        await pool.disconnect(inuse_connections=True)


__all__ = [
    "check_redis_connection",
    "close_redis",
    "get_redis_client",
    "get_redis_pool",
]
