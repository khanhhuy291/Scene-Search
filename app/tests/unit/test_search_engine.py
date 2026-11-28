"""Five vector modes against real in-memory Qdrant and published-run boundaries."""

from types import SimpleNamespace
from uuid import UUID

import pytest
from qdrant_client import AsyncQdrantClient, models

from schemas.search import SearchFilters
from search.cursor import CursorError
from search.engine import MODE_VECTORS, SceneSearchEngine


def uid(n):
    return str(UUID(int=n))


class Encoder:
    dimension = 2

    def __init__(self, version):
        self.model_version = version
        self.calls = []

    def encode_texts(self, texts):
        self.calls.append(texts)
        return [[1.0, 0.0]]


def chunk(n, *, video=1, run="active", caption=True, privacy="verified", version="qwen-v1"):
    vectors = {"siglip": [1.0, 0.0], "qwen": [1.0, 0.0]}
    if caption:
        vectors["caption"] = [1.0, 0.0]
    return models.PointStruct(
        id=uid(n),
        vector=vectors,
        payload={
            "video_id": uid(video),
            "ingestion_run_id": run,
            "privacy_status": privacy,
            "granularity": "segment",
            "siglip_embedding_version": "siglip-v1",
            "qwen_embedding_version": version,
            "caption_embedding_version": version if caption else None,
            "caption_embedding_status": "ready" if caption else "not_available",
            "ts_start_s": n,
            "ts_end_s": n + 4,
            "frame_id": n,
            "caption": "A caption unrelated to the query text.",
            "dataset": "uploads",
            "weather": "rain",
            "object_counts": {"car": 2},
        },
    )


@pytest.fixture
async def corpus(monkeypatch):
    from core.config import get_settings

    settings = get_settings().qdrant
    settings.chunk_collection = "chunks"
    settings.keyframe_collection = "frames"
    client = AsyncQdrantClient(":memory:")
    await client.create_collection(
        "chunks",
        vectors_config={
            key: models.VectorParams(size=2, distance=models.Distance.COSINE)
            for key in ["siglip", "qwen", "caption"]
        },
    )
    await client.create_collection(
        "frames",
        vectors_config={"siglip": models.VectorParams(size=2, distance=models.Distance.COSINE)},
    )
    publications = {uid(1): "active", uid(2): "active", uid(3): "active"}

    async def active(scope=None):
        return {
            video: run for video, run in publications.items() if scope is None or video in scope
        }

    monkeypatch.setattr("search.engine.active_publications", active)
    encoders = {"siglip": Encoder("siglip-v1"), "qwen": Encoder("qwen-v1")}
    engine = SceneSearchEngine(client=client, encoders=encoders)
    yield SimpleNamespace(
        client=client, engine=engine, encoders=encoders, publications=publications
    )
    await client.close()


@pytest.mark.parametrize("mode", list(MODE_VECTORS))
async def test_five_modes_use_exact_vectors_and_unchanged_query(corpus, mode, monkeypatch):
    await corpus.client.upsert("chunks", points=[chunk(10)])
    actual_queries = []
    original = corpus.client.query_points

    async def query(**kwargs):
        actual_queries.append(kwargs)
        return await original(**kwargs)

    monkeypatch.setattr(corpus.client, "query_points", query)
    result = await corpus.engine.search("đường mưa without people", mode=mode, explain=True)
    names = MODE_VECTORS[mode]
    assert [query["using"] for query in actual_queries] == list(names)
    assert all(query["collection_name"] == "chunks" for query in actual_queries)
    assert all("score_threshold" not in query for query in actual_queries)
    for tower, encoder in corpus.encoders.items():
        requested = (tower == "siglip" and "siglip" in names) or (
            tower == "qwen" and any(name != "siglip" for name in names)
        )
        assert encoder.calls == ([["đường mưa without people"]] if requested else [])
    assert result.parsed.semantic_text == "đường mưa without people"
    assert not result.parsed.required and not result.parsed.excluded
    assert result.signals_used == ((*names, "rrf") if len(names) == 2 else names)
    assert len(result.matches) == 1
    expected = 2 / 61 if len(names) == 2 else 1.0
    assert result.matches[0].score == pytest.approx(expected)
    assert set(result.matches[0].signals) == set(names)
    assert not result.exhaustive


async def test_caption_missing_is_excluded_only_from_caption_tower(corpus):
    await corpus.client.upsert("chunks", points=[chunk(10, caption=False), chunk(20, video=2)])
    caption = await corpus.engine.search("rain", mode="caption")
    qwen = await corpus.engine.search("rain", mode="qwen")
    hybrid = await corpus.engine.search("rain", mode="qwen_caption_rrf")
    assert caption.total_videos == 1 and caption.matches[0].keyframe.video_id == uid(2)
    assert qwen.total_videos == hybrid.total_videos == 2
    assert hybrid.matches[0].keyframe.video_id == uid(2)


async def test_rrf_uses_ranks_instead_of_cosine_scale(corpus):
    a, b, c = chunk(10), chunk(20, video=2), chunk(30, video=3)
    a.vector.update(siglip=[1.0, 0.0], qwen=[0.0, 1.0])
    b.vector.update(siglip=[0.8, 0.6], qwen=[1.0, 0.0])
    c.vector.update(siglip=[0.0, 1.0], qwen=[0.8, 0.6])
    await corpus.client.upsert("chunks", points=[a, b, c])
    result = await corpus.engine.search("rain", mode="siglip_qwen_rrf", explain=True)
    assert result.matches[0].keyframe.point_id == uid(20)
    assert result.matches[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert result.matches[0].signals == pytest.approx({"siglip": 1 / 62, "qwen": 1 / 61})


async def test_only_active_private_safe_matching_model_publications_are_searched(corpus):
    await corpus.client.upsert(
        "chunks",
        points=[
            chunk(10),
            chunk(20, run="staged"),
            chunk(30, privacy="unverified"),
            chunk(40, version="old-model"),
            chunk(50, video=9),
        ],
    )
    result = await corpus.engine.search("rain", mode="qwen")
    assert [m.keyframe.point_id for m in result.matches] == [uid(10)]
    assert result.total_keyframes == 1


async def test_explicit_filters_and_optional_cosine_cutoff(corpus):
    a, b, c = chunk(10), chunk(20, video=2), chunk(30, video=3)
    b.payload["object_counts"]["car"] = 1
    c.vector["qwen"] = [0.0, 1.0]
    await corpus.client.upsert("chunks", points=[a, b, c])
    result = await corpus.engine.search(
        "rain",
        mode="qwen",
        min_score=0.5,
        filters=SearchFilters(dataset=["uploads"], weather=["rain"], min_object_counts={"car": 2}),
    )
    assert [m.keyframe.point_id for m in result.matches] == [uid(10)]
    scoped = await corpus.engine.search(
        "rain", mode="qwen", video_ids=[uid(2)], filters=SearchFilters(video_ids=[uid(1)])
    )
    assert not scoped.matches


async def test_grouping_and_cursor_bind_mode_and_publication(corpus):
    await corpus.client.upsert(
        "chunks", points=[chunk(10), chunk(11), chunk(20, video=2), chunk(30, video=3)]
    )
    first = await corpus.engine.search("rain", mode="qwen", limit=1)
    second = await corpus.engine.search("rain", mode="qwen", limit=1, cursor=first.next_cursor)
    third = await corpus.engine.search("rain", mode="qwen", limit=1, cursor=second.next_cursor)
    assert [page.matches[0].keyframe.video_id for page in [first, second, third]] == [
        uid(1),
        uid(2),
        uid(3),
    ]
    assert first.matches[0].keyframes_matched == 2
    assert first.total_keyframes == 4
    assert third.next_cursor is None
    with pytest.raises(CursorError):
        await corpus.engine.search("rain", mode="caption", limit=1, cursor=first.next_cursor)
    corpus.publications[uid(1)] = "next-run"
    with pytest.raises(CursorError):
        await corpus.engine.search("rain", mode="qwen", limit=1, cursor=first.next_cursor)


async def test_publication_changed_mid_request_retries_before_return(corpus, monkeypatch):
    await corpus.client.upsert("chunks", points=[chunk(10), chunk(20, video=2)])
    original = corpus.client.retrieve
    calls = []

    async def retrieve(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            corpus.publications[uid(1)] = "new-run"
        return await original(**kwargs)

    monkeypatch.setattr(corpus.client, "retrieve", retrieve)
    result = await corpus.engine.search("rain", mode="qwen")
    assert [m.keyframe.video_id for m in result.matches] == [uid(2)]
    assert len(calls) == 2


async def test_caption_payload_changes_are_retried_not_returned_stale(corpus, monkeypatch):
    await corpus.client.upsert("chunks", points=[chunk(10)])
    original = corpus.client.retrieve
    count = 0

    async def retrieve(**kwargs):
        nonlocal count
        count += 1
        if count == 1:
            await corpus.client.set_payload(
                "chunks", points=[uid(10)], payload={"caption": "new caption"}
            )
        return await original(**kwargs)

    monkeypatch.setattr(corpus.client, "retrieve", retrieve)
    result = await corpus.engine.search("rain", mode="caption")
    assert result.matches[0].keyframe.caption == "new caption"


async def test_selected_tower_error_does_not_silently_fallback(corpus, monkeypatch):
    await corpus.client.upsert("chunks", points=[chunk(10)])
    original = corpus.client.query_points

    async def query(**kwargs):
        if kwargs["using"] == "caption":
            raise RuntimeError("caption tower unavailable")
        return await original(**kwargs)

    monkeypatch.setattr(corpus.client, "query_points", query)
    with pytest.raises(RuntimeError, match="caption tower unavailable"):
        await corpus.engine.search("rain", mode="qwen_caption_rrf")


async def test_frame_requests_use_actual_siglip_keyframe_index(corpus):
    await corpus.client.upsert(
        "frames",
        points=[
            models.PointStruct(
                id=uid(10),
                vector={"siglip": [1.0, 0.0]},
                payload={
                    "video_id": uid(1),
                    "ingestion_run_id": "active",
                    "model_version": "siglip-v1",
                    "privacy_status": "verified",
                    "granularity": "frame",
                    "ts_start_s": 2,
                    "ts_end_s": 2,
                },
            )
        ],
    )
    result = await corpus.engine.search("rain", mode="siglip", granularity="frame")
    assert result.matches[0].keyframe.granularity == "frame"
    with pytest.raises(ValueError, match="SigLIP only"):
        await corpus.engine.search("rain", mode="caption", granularity="frame")


async def test_empty_published_corpus_does_not_search_legacy_or_load_models(corpus):
    corpus.publications.clear()
    result = await corpus.engine.search("rain", mode="caption")
    assert not result.matches
    assert result.signals_used == ()
    assert result.model_version == "not_queried"
    assert all(not encoder.calls for encoder in corpus.encoders.values())
