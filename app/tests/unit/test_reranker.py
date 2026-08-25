"""Unit tests for the Qwen VL cross-encoder reranker module."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from ml.reranker import QwenVLReranker
from search.catalog import Keyframe, KeyframeCatalog
from search.engine import SceneSearchEngine, VideoMatch


def make_keyframe(
    point_id: str, caption: str, scene_type: str = "highway", time_of_day: str = "day"
) -> Keyframe:
    return Keyframe(
        point_id=point_id,
        video_id=f"vid_{point_id}",
        timestamp_s=10.0,
        frame_no=100,
        thumbnail_key=f"thumbs/{point_id}.jpg",
        video_key=f"videos/{point_id}.mov",
        caption=caption,
        scene_type=scene_type,
        time_of_day=time_of_day,
        retrieval_tags=("car", "fast"),
    )


def make_match(kf: Keyframe, score: float) -> VideoMatch:
    return VideoMatch(
        keyframe=kf,
        score=score,
        keyframes_matched=1,
        keyframes_in_video=5,
        signals={"qwen": score},
    )


def test_build_doc_text() -> None:
    reranker = QwenVLReranker()
    kf = make_keyframe("p1", "A fast red car on the highway", "highway", "night")
    doc = reranker._build_doc_text(kf)
    assert "A fast red car on the highway" in doc
    assert "Scene: highway" in doc
    assert "Time: night" in doc
    assert "Tags: car, fast" in doc


def test_reranker_reorders_candidates() -> None:
    kf1 = make_keyframe("p1", "A bicycle on sidewalk")
    kf2 = make_keyframe("p2", "A red sports car speeding")

    m1 = make_match(kf1, 0.9)
    m2 = make_match(kf2, 0.8)

    reranker = QwenVLReranker()
    fake_model = MagicMock()
    # CrossEncoder returns rank items with corpus_id and score
    fake_model.rank.return_value = [
        {"corpus_id": 1, "score": 0.99},  # m2 is more relevant
        {"corpus_id": 0, "score": 0.12},  # m1 is less relevant
    ]
    reranker._model = fake_model

    reranked = reranker.rerank("red sports car", [m1, m2])
    assert len(reranked) == 2
    assert reranked[0].keyframe.point_id == "p2"
    assert reranked[0].score > reranked[1].score
    assert reranked[0].signals["rerank"] == reranked[0].score
    assert reranked[1].keyframe.point_id == "p1"


def test_reranker_fallback_on_failure() -> None:
    kf1 = make_keyframe("p1", "Caption 1")
    kf2 = make_keyframe("p2", "Caption 2")
    m1 = make_match(kf1, 0.9)
    m2 = make_match(kf2, 0.8)

    reranker = QwenVLReranker()
    fake_model = MagicMock()
    fake_model.rank.side_effect = RuntimeError("GPU out of memory")
    reranker._model = fake_model

    # On error, it should not throw but return original candidates gracefully
    res = reranker.rerank("query", [m1, m2])
    assert len(res) == 2
    assert res[0].keyframe.point_id == "p1"
    assert res[1].keyframe.point_id == "p2"


@pytest.mark.asyncio
async def test_engine_search_with_rerank() -> None:
    from .test_search_engine import FakeEncoder, FakeQdrant, keyframe

    points = [
        keyframe("p1", "video-a", "A blue car on the road."),
        keyframe("p2", "video-b", "A red sports car on the highway."),
    ]
    client = FakeQdrant(points, scores={"p1": 0.8, "p2": 0.7})
    engine = SceneSearchEngine(
        client=client,
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )

    with patch("ml.reranker.get_reranker") as mock_get_reranker:
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = lambda query, matches, top_k: [
            replace(matches[1], score=0.98, signals={**matches[1].signals, "rerank": 0.98}),
            replace(matches[0], score=0.15, signals={**matches[0].signals, "rerank": 0.15}),
        ]
        mock_get_reranker.return_value = mock_reranker

        outcome = await engine.search("red sports car", limit=5, mode="qwen", rerank=True)

        assert "rerank" in outcome.signals_used
        assert len(outcome.matches) == 2
        assert outcome.matches[0].keyframe.point_id == "p2"
        assert outcome.matches[0].score == 0.98
        assert outcome.matches[1].keyframe.point_id == "p1"
        assert outcome.matches[1].score == 0.15
