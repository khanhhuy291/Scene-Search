"""Deterministic synthetic points for a seeded index.

The value of a seeded index is that it exercises real Qdrant behaviour — payload
indexes, prefiltering, batching, id collisions — before anything is ingested. So
what these tests assert is that the points are structurally indistinguishable
from real ones, and reproducible.
"""

from __future__ import annotations

import math

import pytest

from search.points import point_id
from search.seed import build_seed_points, deterministic_vector, seed_qdrant

pytest.importorskip("qdrant_client", reason="qdrant-client is a core dependency")

DIM = 768


class _FakeQdrant:
    def __init__(self) -> None:
        self.points: list[object] = []

    async def upsert(self, *, collection_name: str, points: list[object], wait: bool) -> None:
        self.points.extend(points)


def test_vectors_are_unit_length() -> None:
    # The collection uses cosine distance and every real vector arrives
    # normalised. An unnormalised seed would behave differently under int8
    # quantisation and quietly invalidate any latency comparison.
    v = deterministic_vector("frame", "abc", dimension=DIM)
    assert len(v) == DIM
    assert math.sqrt(sum(x * x for x in v)) == pytest.approx(1.0, abs=1e-9)


def test_vectors_span_the_sphere_rather_than_one_orthant() -> None:
    # All-positive vectors would make every pair similar, so a filtered search
    # would look like it works while ranking was meaningless.
    v = deterministic_vector("frame", "abc", dimension=DIM)
    assert min(v) < 0 < max(v)


def test_the_same_inputs_always_produce_the_same_vector() -> None:
    assert deterministic_vector("frame", "x", dimension=64) == deterministic_vector(
        "frame", "x", dimension=64
    )


def test_different_inputs_produce_different_vectors() -> None:
    assert deterministic_vector("frame", "x", dimension=64) != deterministic_vector(
        "frame", "y", dimension=64
    )


def test_point_counts_match_the_requested_shape() -> None:
    points, seeded = build_seed_points(videos=3, segments_per_video=2, frames_per_segment=4)
    # 3 videos x 2 segments x (4 frames + 1 segment point)
    assert len(points) == 3 * 2 * (4 + 1)
    assert len(seeded) == 3
    assert len(seeded[0].frame_ids) == 8
    assert len(seeded[0].segment_ids) == 2


def test_ids_are_derived_the_same_way_real_ones_are() -> None:
    # Re-indexing must overwrite, not duplicate. Seeded points have to share that
    # property or the seeded index stops resembling the real one.
    _, seeded = build_seed_points(videos=1, segments_per_video=1, frames_per_segment=1)
    frame_id = seeded[0].frame_ids[0]
    assert point_id("frame", frame_id) != point_id("segment", frame_id)


def test_seeding_twice_produces_identical_points() -> None:
    first, _ = build_seed_points(videos=2, segments_per_video=2, frames_per_segment=2)
    second, _ = build_seed_points(videos=2, segments_per_video=2, frames_per_segment=2)
    assert [p.id for p in first] == [p.id for p in second]
    assert [p.vector for p in first] == [p.vector for p in second]


def test_payloads_carry_every_filterable_field() -> None:
    # If a seeded payload omits a field, the filter that uses it is never
    # exercised and its first real test is against real data.
    points, _ = build_seed_points(videos=1, segments_per_video=1, frames_per_segment=1)
    payload = points[0].payload
    for key in (
        "video_id",
        "dataset",
        "granularity",
        "ts_start_s",
        "ts_end_s",
        "model_version",
        "objects",
        "object_counts",
        "behaviors",
        "weather",
        "timeofday",
        "scene",
        "split",
    ):
        assert key in payload, f"seeded payload is missing {key!r}"


def test_both_granularities_are_present_and_distinguishable() -> None:
    points, _ = build_seed_points(videos=1, segments_per_video=2, frames_per_segment=3)
    kinds = {p.payload["granularity"] for p in points}
    assert kinds == {"frame", "segment"}


def test_a_segment_spans_its_frames() -> None:
    points, _ = build_seed_points(videos=1, segments_per_video=1, frames_per_segment=5)
    segment = next(p for p in points if p.payload["granularity"] == "segment")
    frames = [p for p in points if p.payload["granularity"] == "frame"]
    assert segment.payload["ts_start_s"] <= min(f.payload["ts_start_s"] for f in frames)
    assert segment.payload["ts_end_s"] >= max(f.payload["ts_end_s"] for f in frames)


def test_behaviours_are_present_on_some_videos_and_absent_on_others() -> None:
    # A filter needs both matches and non-matches to be worth anything.
    _, seeded = build_seed_points(videos=12, segments_per_video=1, frames_per_segment=1)
    with_behaviour = [s for s in seeded if s.behaviors]
    assert 0 < len(with_behaviour) < len(seeded)


def test_a_small_corpus_still_yields_a_behaviour_to_filter_on() -> None:
    # Caught by an end-to-end run: with hash-keyed assignment, six videos
    # produced zero behaviours and the behaviour filter went untested while
    # appearing to pass. Index-keyed assignment guarantees coverage.
    for videos in (1, 2, 3, 6):
        _, seeded = build_seed_points(videos=videos, segments_per_video=1, frames_per_segment=1)
        assert any(s.behaviors for s in seeded), f"no behaviour with videos={videos}"
    _, seeded = build_seed_points(videos=2, segments_per_video=1, frames_per_segment=1)
    assert not all(s.behaviors for s in seeded), "need non-matches too"


def test_invalid_shapes_are_rejected() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        build_seed_points(videos=0)
    with pytest.raises(ValueError, match=">= 1"):
        build_seed_points(segments_per_video=0)


async def test_seed_qdrant_writes_every_point() -> None:
    client = _FakeQdrant()
    written, seeded = await seed_qdrant(
        videos=2, segments_per_video=2, frames_per_segment=2, client=client
    )
    assert written == 2 * 2 * (2 + 1)
    assert len(client.points) == written
    assert len(seeded) == 2
