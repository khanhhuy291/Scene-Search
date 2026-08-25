"""Security utilities for hashing passwords and managing JWT tokens."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt
from loguru import logger

from core.config import get_settings
from infrastructure.redis import get_redis_client


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt-hashed password."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash from a plain-text password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(
    subject: str | UUID,
    role: str,
    token_version: int = 0,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Encode a new JWT access token with role, type, and expiration claims."""
    settings = get_settings()
    now = datetime.now(UTC)

    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.auth.access_token_expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "token_version": token_version,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.auth.secret_key.get_secret_value(),
        algorithm=settings.auth.algorithm,
    )


def create_refresh_token(
    subject: str | UUID,
    role: str,
    token_version: int = 0,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Encode a new JWT refresh token with extended expiration."""
    settings = get_settings()
    now = datetime.now(UTC)

    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.auth.refresh_token_expire_days)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "token_version": token_version,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.auth.secret_key.get_secret_value(),
        algorithm=settings.auth.algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate any JWT token (access or refresh).

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid or corrupted.
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.auth.secret_key.get_secret_value(),
        algorithms=[settings.auth.algorithm],
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token specifically."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token is not a valid access token")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT refresh token specifically."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Token is not a valid refresh token")
    return payload


async def blacklist_token(token: str, exp: int | None = None) -> None:
    """Add a token hash to the revocation blacklist in Redis until expiration."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        redis = get_redis_client()
        ttl = 86400 * 7  # default 7 days
        if exp is not None:
            now_ts = int(datetime.now(UTC).timestamp())
            ttl = max(1, exp - now_ts)
        await redis.set(f"bl_{token_hash}", "revoked", ex=ttl)
    except Exception as exc:
        logger.warning("Could not blacklist token in Redis: {error}", error=exc)


async def is_token_blacklisted(token: str) -> bool:
    """Check if a token has been revoked / logged out."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        redis = get_redis_client()
        result = await redis.get(f"bl_{token_hash}")
        return result is not None
    except Exception:
        # If Redis is offline in standalone dev mode, treat as unrevoked
        return False


__all__ = [
    "blacklist_token",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "decode_token",
    "get_password_hash",
    "is_token_blacklisted",
    "verify_password",
]
