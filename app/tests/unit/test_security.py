"""Unit tests for password hashing, JWT access/refresh tokens, and token blacklisting."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
import pytest

from core.config import AppSettings, AuthSettings, Settings
from core.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    decode_token,
    get_password_hash,
    is_token_blacklisted,
    verify_password,
)
from db.models.review import UserRole


def test_password_hashing_and_verification() -> None:
    """Test that passwords are correctly hashed and verified."""
    raw_password = "SecretPassword123!"
    hashed = get_password_hash(raw_password)

    assert hashed != raw_password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_access_token_generation_and_decoding() -> None:
    """Test generating a valid JWT access token and decoding its claims."""
    user_id = uuid4()
    role = UserRole.ENGINEER.value
    email = "engineer@scenesearch.ai"

    token = create_access_token(
        subject=user_id,
        role=role,
        extra_claims={"email": email},
    )
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == role
    assert payload["token_version"] == 0
    assert payload["type"] == "access"
    assert payload["email"] == email
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_refresh_token_generation_and_decoding() -> None:
    """Test generating a valid JWT refresh token."""
    user_id = uuid4()
    role = UserRole.ENGINEER.value

    token = create_refresh_token(subject=user_id, role=role)
    payload = decode_refresh_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["role"] == role
    assert payload["token_version"] == 0
    assert payload["type"] == "refresh"

    # Assert passing refresh token to decode_access_token raises InvalidTokenError
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_jwt_token_expiration() -> None:
    """Test that expired tokens raise jwt.ExpiredSignatureError."""
    user_id = uuid4()
    role = UserRole.ADMIN.value

    token = create_access_token(
        subject=user_id,
        role=role,
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_jwt_token_invalid_signature() -> None:
    """Test that tampered tokens raise jwt.InvalidTokenError."""
    user_id = uuid4()
    token = create_access_token(subject=user_id, role="engineer")
    tampered_token = token[:-5] + "ABCDE"

    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered_token)


def test_production_rejects_the_default_jwt_secret() -> None:
    with pytest.raises(ValueError, match="AUTH_SECRET_KEY must be explicitly configured"):
        Settings(app=AppSettings(env="production"))


def test_production_accepts_an_explicit_jwt_secret() -> None:
    settings = Settings(
        app=AppSettings(env="production"),
        auth=AuthSettings(secret_key="a-production-only-secret-that-is-long-enough"),
    )

    assert settings.app.env == "production"


@pytest.mark.asyncio
async def test_token_blacklisting_redis_integration() -> None:
    """Test blacklist_token and is_token_blacklisted with mocked Redis."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "revoked"

    with patch("core.security.get_redis_client", return_value=mock_redis):
        token = "mock.jwt.token"
        await blacklist_token(token, exp=None)
        mock_redis.set.assert_called_once()

        revoked = await is_token_blacklisted(token)
        assert revoked is True
