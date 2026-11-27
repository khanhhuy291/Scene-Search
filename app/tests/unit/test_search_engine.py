"""Vector retrieval contract: exact query/tower, score order, RRF, filters and paging."""

from types import SimpleNamespace

import pytest
from qdrant_client import AsyncQdrantClient, models

from core.config import get_settings
from schemas.search import SearchFilters
from search.cursor import CursorError
from search.engine import SceneSearchEngine


class Encoder:
    def __init__(self, vector):
        self.vector = vector
        self.calls = []

    def encode_texts(self, texts):
        self.calls.append(texts)
        return [self.vector]


def point(pid, score, video=None):
    return SimpleNamespace(
        id=pid,
        score=score,
        payload={
            "video_id": video or pid,
            "caption": "unrelated caption",
            "timestamp_s": 2.0,
        },
    )


class Qdrant:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def query_points(self, **kwargs):
        self.calls.append(kwargs)
        points = self.routes[kwargs["using"]]
        if isinstance(points, Exception):
            raise points
        return SimpleNamespace(points=points)


def engine(routes):
    client = Qdrant(routes)
    encoders = {"siglip": Encoder([1.0, 0.0]), "qwen": Encoder([0.0, 1.0])}
    return SceneSearchEngine(client=client, encoders=encoders), client, encoders


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["siglip", "qwen"])
async def test_single_tower_embeds_unchanged_query_and_preserves_cosine_order(mode):
    search, client, encoders = engine({mode: [point("a", 0.8), point("b", 0.3)]})
    query = "đường mưa without pedestrians"
    result = await search.search(query, mode=mode, explain=True)
    assert encoders[mode].calls == [[query]]
    assert encoders["qwen" if mode == "siglip" else "siglip"].calls == []
    assert client.calls[0]["using"] == mode
    assert client.calls[0]["query"] == encoders[mode].vector
    assert "score_threshold" not in client.calls[0]
    assert [(m.keyframe.point_id, m.score) for m in result.matches] == [("a", 0.8), ("b", 0.3)]
    assert result.signals_used == (mode,)
    assert result.parsed.semantic_text == query
    assert not result.parsed.required and not result.parsed.excluded
    assert result.exhaustive is False


@pytest.mark.asyncio
async def test_hybrid_always_queries_both_and_uses_equal_weight_rrf():
    search, client, encoders = engine(
        {
            "siglip": [point("a", 0.9), point("b", 0.8)],
            "qwen": [point("b", 0.99), point("c", 0.9)],
        }
    )
    result = await search.search("rain", mode="hybrid", explain=True)
    assert {call["using"] for call in client.calls} == {"siglip", "qwen"}
    assert all(encoder.calls == [["rain"]] for encoder in encoders.values())
    assert [m.keyframe.point_id for m in result.matches] == ["b", "a", "c"]
    assert result.matches[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert result.matches[0].signals == pytest.approx({"siglip": 1 / 62, "qwen": 1 / 61})
    assert result.signals_used == ("siglip", "qwen", "rrf")


@pytest.mark.asyncio
async def test_hybrid_failure_is_not_silently_downgraded():
    search, _, _ = engine({"siglip": [point("a", 0.8)], "qwen": RuntimeError("offline")})
    with pytest.raises(RuntimeError, match="offline"):
        await search.search("rain", mode="hybrid")


@pytest.mark.asyncio
async def test_encoder_failure_is_not_hidden():
    search, _, encoders = engine({"qwen": []})

    def fail(texts):
        raise RuntimeError("encoder offline")

    encoders["qwen"].encode_texts = fail
    with pytest.raises(RuntimeError, match="encoder offline"):
        await search.search("rain", mode="qwen")


@pytest.mark.asyncio
async def test_explicit_selection_overrides_server_default():
    get_settings().search.mode = "qwen"
    search, client, _ = engine({"siglip": []})
    await search.search("rain", mode="siglip")
    assert client.calls[0]["using"] == "siglip"


@pytest.mark.asyncio
async def test_grouping_keeps_best_vector_match_even_without_media():
    search, _, _ = engine({"qwen": [point("a", 0.9, "v"), point("b", 0.8, "v")]})
    result = await search.search("rain", mode="qwen")
    assert result.total_videos == 1 and result.total_keyframes == 2
    assert result.matches[0].keyframe.point_id == "a"
    assert result.matches[0].keyframes_matched == 2
    assert len(result.matches[0].matched_keyframes) == 2


@pytest.mark.asyncio
async def test_pagination_and_foreign_mode_cursor():
    search, _, _ = engine({"qwen": [point("a", 0.8), point("b", 0.8), point("c", 0.6)]})
    first = await search.search("rain", mode="qwen", limit=1)
    second = await search.search("rain", mode="qwen", limit=1, cursor=first.next_cursor)
    third = await search.search("rain", mode="qwen", limit=1, cursor=second.next_cursor)
    assert [r.matches[0].keyframe.point_id for r in [first, second, third]] == ["a", "b", "c"]
    assert third.next_cursor is None
    with pytest.raises(CursorError):
        await search.search("rain", mode="siglip", limit=1, cursor=first.next_cursor)


@pytest.mark.asyncio
async def test_payload_filters_and_score_cutoff_on_real_qdrant():
    # In-memory Qdrant validates actual named-vector and filter API semantics.
    client = AsyncQdrantClient(":memory:")
    await client.create_collection(
        "scenes",
        vectors_config={
            name: models.VectorParams(size=2, distance=models.Distance.COSINE)
            for name in ["siglip", "qwen"]
        },
    )
    await client.upsert(
        "scenes",
        points=[
            models.PointStruct(
                id=i,
                vector={"siglip": vector, "qwen": vector},
                payload={
                    "video_id": f"v{i}",
                    "dataset": "uploads",
                    "weather": weather,
                    "object_counts": {"car": count},
                    "granularity": "frame",
                },
            )
            for i, vector, weather, count in [
                (1, [1.0, 0.0], "rain", 2),
                (2, [1.0, 0.0], "sun", 2),
                (3, [1.0, 0.0], "rain", 1),
                (4, [0.0, 1.0], "rain", 2),
            ]
        ],
    )
    search = SceneSearchEngine(client=client, encoder=Encoder([1.0, 0.0]), collection="scenes")
    result = await search.search(
        "rain",
        mode="hybrid",
        min_score=0.5,
        granularity="frame",
        filters=SearchFilters(dataset=["uploads"], weather=["rain"], min_object_counts={"car": 2}),
    )
    assert [m.keyframe.video_id for m in result.matches] == ["v1"]
    await client.close()


@pytest.mark.asyncio
async def test_no_candidates_is_empty_not_lexical_fallback():
    search, _, _ = engine({"siglip": []})
    result = await search.search("rain", mode="siglip")
    assert not result.matches and result.total_videos == 0
    assert not result.below_threshold
