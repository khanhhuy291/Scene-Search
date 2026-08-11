"""Async SQLAlchemy engine and FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from loguru import logger
from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import DatabaseSettings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def database_url(settings: DatabaseSettings) -> URL:
    """Build a SQLAlchemy URL whose string representation masks the password."""

    if settings.url:
        return make_url(settings.url)
    return URL.create(
        drivername="postgresql+asyncpg",
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )


def get_engine() -> AsyncEngine:
    """Create and return the process-wide async database engine."""

    global _engine, _session_factory
    if _engine is None:
        settings = get_settings().database
        _engine = create_async_engine(
            database_url(settings),
            echo=settings.echo,
            pool_pre_ping=True,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout,
            pool_recycle=settings.pool_recycle,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared async-session factory."""

    get_engine()
    if _session_factory is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("Database session factory was not initialized")
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a transaction-safe SQLAlchemy session for FastAPI dependencies."""

    session = get_session_factory()()
    try:
        yield session
    except BaseException:
        try:
            await session.rollback()
        except Exception:
            logger.exception("Failed to roll back database session")
        raise
    finally:
        try:
            await session.close()
        except Exception:
            logger.exception("Failed to close database session")


async def close_postgres() -> None:
    """Dispose of the engine and its connection pool during app shutdown."""

    global _engine, _session_factory
    engine, _engine, _session_factory = _engine, None, None
    if engine is not None:
        await engine.dispose()


__all__ = [
    "close_postgres",
    "database_url",
    "get_db_session",
    "get_engine",
    "get_session_factory",
]
