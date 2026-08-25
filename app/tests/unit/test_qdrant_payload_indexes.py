"""Payload-index bootstrap for Qdrant.

These indexes are what make metadata filtering prune the HNSW search instead of
discarding results after it. A missing index does not fail loudly; it just makes
filtered queries slow, so it is worth asserting.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrastructure import qdrant as qdrant_module


class _FakeQdrant:
    def __init__(self, *, failures: dict[str, Exception] | None = None) -> None:
        self.created: list[str] = []
        self._failures = failures or {}

    async def create_payload_index(
        self, *, collection_name: str, field_name: str, field_schema: Any, wait: bool
    ) -> None:
        if field_name in self._failures:
            raise self._failures[field_name]
        self.created.append(field_name)


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Any:
    qdrant_module.get_settings.cache_clear()
    yield
    qdrant_module.get_settings.cache_clear()


async def test_every_filterable_field_is_indexed() -> None:
    client = _FakeQdrant()
    created = await qdrant_module.ensure_payload_indexes(client)

    # Each of these backs a filter exposed in SearchFilters. Dropping one
    # silently turns that filter into a full scan.
    required = {
        "video_id",
        "dataset",
        "split",
        "weather",
        "timeofday",
        "scene",
        "objects",
        "behaviors",
        "granularity",
        "model_version",
        "ts_start_s",
    }
    assert required <= set(created)
    assert set(created) == set(client.created)


async def test_existing_indexes_are_tolerated() -> None:
    # Startup runs on every boot, so the steady state is that every index
    # already exists. That must not be an error.
    client = _FakeQdrant(
        failures={"weather": RuntimeError("Index already exists for field weather")}
    )
    created = await qdrant_module.ensure_payload_indexes(client)
    assert "weather" not in created
    assert "timeofday" in created


async def test_unexpected_failures_are_raised() -> None:
    client = _FakeQdrant(failures={"weather": RuntimeError("connection refused")})
    with pytest.raises(RuntimeError, match="connection refused"):
        await qdrant_module.ensure_payload_indexes(client)


def test_viettech_named_vectors_are_treated_as_hybrid_attach() -> None:
    assert qdrant_module._is_hybrid_named_vectors({"siglip": object(), "bgem3": object()})
    assert qdrant_module._is_hybrid_named_vectors({"siglip_visual": object(), "bge_text": object()})
    assert qdrant_module._is_hybrid_named_vectors({"qwen": object(), "siglip": object()})
    assert qdrant_module.is_read_only_collection({"qwen": object(), "siglip": object()})
    assert not qdrant_module._is_hybrid_named_vectors({"siglip": object()})
