"""Authentication must use a real database user, including during outages."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.deps import get_current_user


@pytest.mark.asyncio
@pytest.mark.parametrize("database_error, expected_status", [(False, 401), (True, 503)])
async def test_auth_never_synthesizes_demo_admin(database_error, expected_status):
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    lookup = AsyncMock(return_value=None)
    if database_error:
        lookup.side_effect = RuntimeError("database unavailable")
    request = Request({"type": "http", "headers": [], "query_string": b""})
    with (
        patch("api.deps.is_token_blacklisted", AsyncMock(return_value=False)),
        patch("api.deps.decode_access_token", return_value={"sub": str(user_id), "role": "admin"}),
        patch("api.deps.UserRepository.get_by_id", lookup),
        pytest.raises(HTTPException) as caught,
    ):
        await get_current_user(request, SimpleNamespace(credentials="signed-token"), AsyncMock())
    assert caught.value.status_code == expected_status


@pytest.mark.asyncio
async def test_login_rejects_demo_credentials_during_database_outage():
    from services.auth import AuthService

    with (
        patch(
            "services.auth.UserRepository.get_by_email",
            AsyncMock(side_effect=RuntimeError("DB offline")),
        ),
        pytest.raises(HTTPException) as caught,
    ):
        await AuthService(AsyncMock()).authenticate_user("admin@scenesearch.ai", "Pass@123456")
    assert caught.value.status_code == 503
