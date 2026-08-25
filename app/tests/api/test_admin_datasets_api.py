"""Admin telemetry, eval report, and dataset export endpoints."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import get_current_user, require_admin, require_engineer_or_admin
from api.main import app
from db.models.review import User, UserRole
from schemas.admin import (
    AdminTelemetry,
    CorpusHealth,
    EvalReportResponse,
    QdrantHealth,
    StorageHealth,
    WorkerHealth,
)
from search.catalog import Keyframe


@pytest.fixture
def mock_engineer() -> User:
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "engineer@scenesearch.ai"
    user.display_name = "Engineer"
    user.role = UserRole.ENGINEER.value
    user.token_version = 0
    user.is_active = True
    return user


@pytest.fixture
def mock_admin() -> User:
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "admin@scenesearch.ai"
    user.display_name = "Admin"
    user.role = UserRole.ADMIN.value
    user.token_version = 0
    user.is_active = True
    return user


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_telemetry_forbidden_for_engineer(client: AsyncClient, mock_engineer: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_engineer
    response = await client.get(
        "/api/v1/admin/telemetry",
        headers={"Authorization": "Bearer mock"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_telemetry_returns_live_payload(client: AsyncClient, mock_admin: User) -> None:
    app.dependency_overrides[require_admin] = lambda: mock_admin
    payload = AdminTelemetry(
        generated_at="2026-08-20T00:00:00+00:00",
        corpus=CorpusHealth(videos=12, keyframes=100, media_coverage_pct=80),
        qdrant=QdrantHealth(reachable=True, collection="Scences", points_count=100),
        storage=StorageHealth(reachable=True),
        workers=WorkerHealth(reachable=True, worker_count=0),
    )
    with patch("api.v1.admin.collect_telemetry", new=AsyncMock(return_value=payload)):
        response = await client.get(
            "/api/v1/admin/telemetry",
            headers={"Authorization": "Bearer mock"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["corpus"]["videos"] == 12
    assert body["qdrant"]["collection"] == "Scences"


@pytest.mark.asyncio
async def test_eval_report_can_be_absent(client: AsyncClient, mock_admin: User) -> None:
    app.dependency_overrides[require_admin] = lambda: mock_admin
    missing = EvalReportResponse(available=False, detail="No eval report on disk.")
    with patch("api.v1.admin.load_eval_report", return_value=missing):
        response = await client.get(
            "/api/v1/admin/eval",
            headers={"Authorization": "Bearer mock"},
        )
    assert response.status_code == 200
    assert response.json()["available"] is False


@pytest.mark.asyncio
async def test_dataset_export_unknown_points(client: AsyncClient, mock_engineer: User) -> None:
    app.dependency_overrides[require_engineer_or_admin] = lambda: mock_engineer
    catalog = MagicMock()
    catalog.ensure_loaded = AsyncMock()
    catalog.get.return_value = None
    with patch("services.datasets.get_catalog", return_value=catalog):
        response = await client.post(
            "/api/v1/datasets/export",
            headers={"Authorization": "Bearer mock"},
            json={
                "dataset_id": "ds_test",
                "title": "Test set",
                "items": [{"point_id": "missing-point"}],
            },
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dataset_export_zip_contains_clip(client: AsyncClient, mock_engineer: User) -> None:
    app.dependency_overrides[require_engineer_or_admin] = lambda: mock_engineer
    frame = Keyframe(
        point_id="p1",
        video_id="video-1",
        timestamp_s=1.5,
        frame_no=10,
        caption="rain",
        thumbnail_key="thumbs/p1.jpg",
        video_key="videos/video-1.mp4",
    )
    catalog = MagicMock()
    catalog.ensure_loaded = AsyncMock()
    catalog.get.return_value = frame

    def fake_read(object_key: str) -> bytes:
        if object_key.endswith(".jpg"):
            return b"thumb-bytes"
        return b"video-bytes"

    with (
        patch("services.datasets.get_catalog", return_value=catalog),
        patch("services.datasets.read_media_object", side_effect=fake_read),
    ):
        response = await client.post(
            "/api/v1/datasets/export",
            headers={"Authorization": "Bearer mock"},
            json={
                "dataset_id": "ds_test",
                "title": "Rain clips",
                "queries": ["rainy day"],
                "items": [{"point_id": "p1", "video_id": "video-1"}],
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    archive = ZipFile(BytesIO(response.content))
    names = set(archive.namelist())
    assert "manifest.jsonl" in names
    assert any(name.startswith("videos/") for name in names)
    assert any(name.startswith("thumbnails/") for name in names)
    manifest = archive.read("manifest.jsonl").decode()
    assert "ds_test" in manifest
    assert "video-1" in manifest
