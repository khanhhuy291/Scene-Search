"""Qdrant payload and filter construction."""

from __future__ import annotations

import pytest

from search.points import ScenePayload, build_filter, build_point, point_id

pytest.importorskip("qdrant_client", reason="qdrant-client is a core dependency")


def payload(**overrides: object) -> ScenePayload:
    base = {
        "frame_id": "frame-1",
        "segment_id": None,
        "video_id": "video-1",
        "dataset": "bdd100k",
        "granularity": "frame",
        "ts_start_s": 10.0,
        "ts_end_s": 10.0,
        "model_version": "siglip-b16-224-v1",
    }
    base.update(overrides)
    return ScenePayload(**base)  # type: ignore[arg-type]


def test_point_ids_are_stable_across_runs() -> None:
    # Re-indexing must overwrite rather than duplicate, so the id has to be a
    # deterministic function of the entity.
    assert point_id("frame", "abc") == point_id("frame", "abc")


def test_frame_and_segment_ids_do_not_collide() -> None:
    # Both granularities share one collection; colliding ids would have a
    # segment silently overwrite its own keyframe.
    assert point_id("frame", "abc") != point_id("segment", "abc")


def test_payload_omits_absent_optional_fields() -> None:
    # Storing explicit nulls bloats the payload index, and Qdrant's IsNull
    # matching is separate from value matching anyway.
    data = payload().to_dict()
    assert "weather" not in data
    assert "segment_id" not in data
    assert data["frame_id"] == "frame-1"


def test_payload_carries_every_filterable_field() -> None:
    data = payload(
        weather="rainy",
        timeofday="night",
        scene="city street",
        split="val",
        objects=["car", "person"],
        object_counts={"car": 3, "person": 1},
        behaviors=["pedestrian_crossing_ego_path"],
    ).to_dict()
    for key in (
        "video_id",
        "dataset",
        "split",
        "granularity",
        "weather",
        "timeofday",
        "scene",
        "objects",
        "object_counts",
        "behaviors",
        "model_version",
        "ts_start_s",
        "ts_end_s",
    ):
        assert key in data, key


def test_object_lists_are_sorted_for_stable_payloads() -> None:
    data = payload(objects=["person", "car"], behaviors=["b", "a"]).to_dict()
    assert data["objects"] == ["car", "person"]
    assert data["behaviors"] == ["a", "b"]


def test_no_constraints_produce_no_filter() -> None:
    # A filter with an empty must clause is not the same as no filter, and
    # passing one would needlessly constrain the search.
    assert build_filter() is None


def test_single_constraint_produces_one_condition() -> None:
    qdrant_filter = build_filter(weather=["rainy"])
    assert qdrant_filter is not None
    assert len(qdrant_filter.must) == 1


def test_objects_all_becomes_one_condition_per_class() -> None:
    """Conjunction over an array field needs separate must entries.

    Qdrant's keyword match on an array is "contains any", so expressing
    "contains car AND contains person" as a single MatchAny would quietly widen
    the query into an OR.
    """

    qdrant_filter = build_filter(objects_all=["car", "person"])
    assert qdrant_filter is not None
    assert len(qdrant_filter.must) == 2


def test_objects_any_becomes_a_single_condition() -> None:
    qdrant_filter = build_filter(objects_any=["car", "person"])
    assert qdrant_filter is not None
    assert len(qdrant_filter.must) == 1


def test_time_range_matches_overlap_not_containment() -> None:
    """A segment straddling the window must still match.

    Requiring containment would drop exactly the results a time filter is meant
    to find: spans that begin before the window and end inside it.
    """

    qdrant_filter = build_filter(time_range_s=(5.0, 10.0))
    assert qdrant_filter is not None
    keys = {condition.key for condition in qdrant_filter.must}
    assert keys == {"ts_end_s", "ts_start_s"}
    by_key = {c.key: c for c in qdrant_filter.must}
    assert by_key["ts_end_s"].range.gte == 5.0
    assert by_key["ts_start_s"].range.lte == 10.0


def test_inverted_time_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="after end"):
        build_filter(time_range_s=(10.0, 5.0))


def test_granularity_and_model_version_are_filterable() -> None:
    # model_version filtering is what lets two encoders coexist during a
    # re-index without returning nonsense from a mixed collection.
    qdrant_filter = build_filter(granularity="segment", model_version="siglip-b16-224-v1")
    assert qdrant_filter is not None
    assert len(qdrant_filter.must) == 2


def test_build_point_uses_the_derived_id_and_payload() -> None:
    point = build_point("frame", "frame-1", [0.1, 0.2, 0.3], payload())
    assert point.id == point_id("frame", "frame-1")
    assert point.vector == [0.1, 0.2, 0.3]
    assert point.payload["video_id"] == "video-1"
