"""Unit tests for RLHF re-ranking feedback submission and dataset export."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from schemas.rlhf import RankedSceneItem, RLHFFeedbackCreate
from services.rlhf import export_rlhf_dataset, save_rlhf_feedback


@pytest.mark.asyncio
async def test_save_and_export_rlhf_feedback():
    item1 = RankedSceneItem(
        scene_id="s1", video_id="v1", timestamp_s=10.0, score=0.9, rank=1, caption="Scene 1"
    )
    item2 = RankedSceneItem(
        scene_id="s2", video_id="v1", timestamp_s=20.0, score=0.8, rank=2, caption="Scene 2"
    )

    payload = RLHFFeedbackCreate(
        query="red car",
        mode="qwen",
        original_ranking=[item1, item2],
        reordered_ranking=[item2, item1],  # User swapped rank 1 and 2
        notes="Scene 2 is clearer",
    )

    mock_session = AsyncMock()
    mock_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch("services.rlhf.get_session_factory", return_value=mock_factory):
        saved = await save_rlhf_feedback(payload)
        assert saved.query == "red car"
        assert len(saved.reordered_ranking) == 2
        assert saved.reordered_ranking[0]["scene_id"] == "s2"


@pytest.mark.asyncio
async def test_export_rlhf_dataset_formats():
    fake_record = MagicMock()
    fake_record.id = uuid4()
    fake_record.query = "traffic lights"
    fake_record.mode = "qwen"
    fake_record.user_email = "admin@scenesearch.ai"
    fake_record.notes = "test"
    fake_record.created_at = MagicMock()
    fake_record.created_at.isoformat.return_value = "2026-08-31T12:00:00Z"
    fake_record.original_ranking = [
        {"scene_id": "s1", "rank": 1, "video_id": "v1"},
        {"scene_id": "s2", "rank": 2, "video_id": "v1"},
    ]
    fake_record.reordered_ranking = [
        {"scene_id": "s2", "rank": 1, "video_id": "v1", "caption": "Green light"},
        {"scene_id": "s1", "rank": 2, "video_id": "v1", "caption": "Red light"},
    ]

    mock_session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [fake_record]
    mock_session.scalars.return_value = mock_scalars
    mock_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch("services.rlhf.get_session_factory", return_value=mock_factory):
        # Pairwise export
        pairwise_data = await export_rlhf_dataset(format_type="pairwise")
        lines = pairwise_data.strip().split("\n")
        assert len(lines) == 1
        pair = json.loads(lines[0])
        assert pair["positive_scene_id"] == "s2"
        assert pair["negative_scene_id"] == "s1"

        # Listwise export
        listwise_data = await export_rlhf_dataset(format_type="listwise")
        list_lines = listwise_data.strip().split("\n")
        assert len(list_lines) == 1
        item = json.loads(list_lines[0])
        assert item["query"] == "traffic lights"
        assert len(item["ranked_scenes"]) == 2


@pytest.mark.asyncio
async def test_feedback_api_submit():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "query": "blue truck",
            "mode": "qwen",
            "original_ranking": [
                {"scene_id": "s1", "rank": 1, "score": 0.8},
                {"scene_id": "s2", "rank": 2, "score": 0.7},
            ],
            "reordered_ranking": [
                {"scene_id": "s2", "rank": 1, "score": 0.7},
                {"scene_id": "s1", "rank": 2, "score": 0.8},
            ],
            "notes": "swapped for testing",
        }

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("services.rlhf.get_session_factory", return_value=mock_factory):
            response = await client.post("/api/v1/feedback/rerank", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["query"] == "blue truck"
            assert data["reordered_ranking"][0]["scene_id"] == "s2"
