"""Ingest is admin-only; media requires a logged-in session. Search stays public."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import get_current_user
from api.main import app
from db.models.review import User, UserRole


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_search_stays_public(client: AsyncClient) -> None:
    from unittest.mock import AsyncMock, patch

    from search.engine import SearchOutcome
    from search.query import parse_query

    empty = SearchOutcome(
        parsed=parse_query("rain"),
        matches=(),
        total_videos=0,
        total_keyframes=0,
        exhaustive=True,
        signals_used=(),
        next_cursor=None,
        took_ms=1.0,
    )
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=empty)
    with patch("api.v1.search.get_search_engine", return_value=engine):
        response = await client.post("/api/v1/search", json={"query": "rain"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_media_allows_optional_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/media/clip/not-a-real-point")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ingest_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/tasks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_is_admin_only(client: AsyncClient) -> None:
    engineer = MagicMock(spec=User)
    engineer.id = uuid4()
    engineer.role = UserRole.ENGINEER.value
    engineer.is_active = True
    engineer.token_version = 0
    app.dependency_overrides[get_current_user] = lambda: engineer
    response = await client.get("/api/v1/tasks", headers={"Authorization": "Bearer mock"})
    assert response.status_code == 403
