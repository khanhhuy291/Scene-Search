"""Qdrant write path.

These tests use a fake client rather than a live Qdrant. What is worth asserting
here is not that qdrant-client works, but that this module batches instead of
sending one request per point, that deletion is scoped to a video across both
granularities, and that a re-index cannot delete the points it just wrote.
"""

from __future__ import annotations

from typing import Any

import pytest

from search import index as index_module
from search.points import ScenePayload, build_point

pytest.importorskip("qdrant_client", reason="qdrant-client is a core dependency")

VECTOR_SIZE = 768


class _FakeQdrant:
    """Records calls instead of performing them."""

    def __init__(self, *, count: int = 0) -> None:
        self.upserts: list[list[Any]] = []
        self.deletes: list[Any] = []
        self.counts: list[Any] = []
        self.order: list[str] = []
        self._count = count

    async def upsert(self, *, collection_name: str, points: list[Any], wait: bool) -> None:
        assert wait is True, "ingestion must not race the integration count"
        self.collection_name = collection_name
        self.upserts.append(points)
        self.order.append("upsert")

    async def delete(self, *, collection_name: str, points_selector: Any, wait: bool) -> None:
        assert wait is True
        self.deletes.append(points_selector)
        self.order.append("delete")

    async def count(self, *, collection_name: str, count_filter: Any, exact: bool) -> Any:
        assert exact is True, "an approximate count makes the frames+segments check flaky"
        self.counts.append(count_filter)

        class _Result:
            count = self._count

        return _Result()


def _payload(**overrides: object) -> ScenePayload:
    base: dict[str, object] = {
        "frame_id": "frame-1",
        "segment_id": None,
        "video_id": "video-1",
        "dataset": "kaggle-driving",
        "granularity": "frame",
        "ts_start_s": 1.0,
        "ts_end_s": 1.0,
        "model_version": "siglip-b16-224-v1",
    }
    base.update(overrides)
    return ScenePayload(**base)  # type: ignore[arg-type]


def _points(n: int, *, dimension: int = VECTOR_SIZE) -> list[Any]:
    return [
        build_point("frame", f"frame-{i}", [0.0] * dimension, _payload(frame_id=f"frame-{i}"))
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Any:
    index_module.get_settings.cache_clear()
    yield
    index_module.get_settings.cache_clear()


async def test_points_are_sent_in_batches() -> None:
    # One request per point over a 6,500-frame corpus is thousands of round
    # trips; the batching is the whole reason this function exists.
    client = _FakeQdrant()
    written = await index_module.upsert_points(_points(5), batch_size=2, client=client)

    assert written == 5
    assert [len(batch) for batch in client.upserts] == [2, 2, 1]


async def test_empty_input_touches_no_client() -> None:
    client = _FakeQdrant()
    assert await index_module.upsert_points([], client=client) == 0
    assert client.upserts == []


async def test_batch_size_must_be_positive() -> None:
    client = _FakeQdrant()
    with pytest.raises(ValueError, match="batch_size"):
        await index_module.upsert_points(_points(1), batch_size=0, client=client)


async def test_wrong_vector_dimension_is_rejected_before_any_request() -> None:
    # A dimension mismatch means two encoders are in use, or one was swapped
    # without rebuilding the collection. Qdrant would reject this mid-batch with
    # an error naming neither side.
    client = _FakeQdrant()
    with pytest.raises(ValueError, match="QDRANT_VECTOR_SIZE"):
        await index_module.upsert_points(_points(3, dimension=512), client=client)
    assert client.upserts == []


async def test_delete_is_scoped_to_the_video_and_not_to_a_granularity() -> None:
    # A video owns both its frame points and its segment points. Deleting only
    # one kind leaves the other pointing at rows the caller is replacing.
    client = _FakeQdrant()
    await index_module.delete_by_video("video-1", client=client)

    assert len(client.deletes) == 1
    conditions = client.deletes[0].filter.must
    keys = {getattr(c, "key", None) for c in conditions}
    assert keys == {"video_id"}


async def test_delete_rejects_an_empty_video_id() -> None:
    # An empty id would build a filter matching nothing, so the call would look
    # successful while deleting nothing -- the failure mode this module exists
    # to prevent.
    client = _FakeQdrant()
    with pytest.raises(ValueError, match="video_id"):
        await index_module.delete_by_video("", client=client)


async def test_count_without_filters_passes_none() -> None:
    client = _FakeQdrant(count=42)
    assert await index_module.count_points(client=client) == 42
    assert client.counts == [None]


async def test_count_can_be_narrowed_by_granularity() -> None:
    client = _FakeQdrant(count=7)
    await index_module.count_points(granularity="segment", client=client)

    conditions = client.counts[0].must
    assert {getattr(c, "key", None) for c in conditions} == {"granularity"}


async def test_reindex_deletes_before_it_writes() -> None:
    # Reversing this deletes the points just written: the delete filter matches
    # on video_id and cannot tell new points from old.
    client = _FakeQdrant()
    await index_module.reindex_video("video-1", _points(2), client=client)

    assert client.order == ["delete", "upsert"]


# -- never write to someone else's collection ---------------------------------


class _HybridCollection:
    """A collection reporting the two-tower layout the read path attaches to."""

    class config:  # noqa: N801
        class params:  # noqa: N801
            vectors = {"siglip": object(), "bgem3": object()}

    async def get_collection(self, name: str) -> _HybridCollection:
        return self

    async def upsert(self, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("the guard should have refused before any write")

    async def delete(self, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("the guard should have refused before any delete")


@pytest.mark.asyncio
async def test_upsert_refuses_a_collection_this_process_does_not_own() -> None:
    # `build_point` has twice been changed to emit a named vector to "match" the
    # attached collection, and both times the name matched neither it nor the one
    # this service creates. A convention did not hold; this makes it structural.
    from search.index import upsert_points

    with pytest.raises(RuntimeError, match="Refusing to write"):
        await upsert_points([object()], client=_HybridCollection())


@pytest.mark.asyncio
async def test_delete_refuses_a_collection_this_process_does_not_own() -> None:
    # The important half. `reindex_video` deletes before it upserts, so without
    # this an ingestion run against the shared index is a pure deletion.
    from search.index import delete_by_video

    with pytest.raises(RuntimeError, match="Refusing to write"):
        await delete_by_video("video-a", client=_HybridCollection())


@pytest.mark.asyncio
async def test_explicit_named_vector_write_wraps_vector(monkeypatch) -> None:
    class _Params:
        size = 2048

    class _WritableHybrid(_FakeQdrant):
        class config:  # noqa: N801
            class params:  # noqa: N801
                vectors = {"qwen": _Params(), "siglip": object()}

        async def get_collection(self, name: str) -> Any:
            return self

    monkeypatch.setenv("QDRANT_VECTOR_SIZE", "2048")
    monkeypatch.setenv("ML_ENCODER_NAME", "Qwen/Qwen3-VL-Embedding-2B")
    monkeypatch.setenv("QDRANT_WRITE_VECTOR_NAME", "qwen")
    monkeypatch.setenv("QDRANT_ALLOW_NAMED_VECTOR_WRITES", "true")
    index_module.get_settings.cache_clear()
    client = _WritableHybrid()

    written = await index_module.upsert_points(_points(1, dimension=2048), client=client)

    assert written == 1
    assert set(client.upserts[0][0].vector) == {"qwen"}
    assert len(client.upserts[0][0].vector["qwen"]) == 2048
