"""Tests for the API-side Qwen model lifecycle guard."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from schemas.admin import EmbeddingModelStatus
from services import embedding_model


def _status(state: str) -> EmbeddingModelStatus:
    return EmbeddingModelStatus(
        state=state,
        model="Qwen/Qwen3-VL-Embedding-2B",
        dimension=2048,
    )


@pytest.mark.asyncio
async def test_ingestion_guard_accepts_ready_and_busy(monkeypatch) -> None:
    request = AsyncMock(side_effect=[_status("ready"), _status("busy")])
    monkeypatch.setattr(embedding_model, "embedding_model_request", request)

    await embedding_model.require_qwen_embedding_ready()
    await embedding_model.require_qwen_embedding_ready()


@pytest.mark.asyncio
async def test_ingestion_guard_rejects_unloaded(monkeypatch) -> None:
    monkeypatch.setattr(
        embedding_model,
        "embedding_model_request",
        AsyncMock(return_value=_status("unloaded")),
    )

    with pytest.raises(HTTPException) as exc:
        await embedding_model.require_qwen_embedding_ready()

    assert exc.value.status_code == 503
    assert "load it before ingesting" in exc.value.detail
