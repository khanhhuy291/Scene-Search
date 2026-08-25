"""Search request and response contracts.

Three callers build against these: the UI, the review flow, and the evaluation
harness. What is worth asserting is the behaviour that is easy to get backwards
-- empty lists collapsing to "no constraint", a fused score not being bounded
like a similarity, and the granularity literal not drifting from the one the
retrieval layer uses.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.search import (
    MAX_LIMIT,
    MAX_QUERY_LENGTH,
    SearchFilters,
    SearchRequest,
    SearchResponse,
    SearchResult,
)


def _result(**overrides: object) -> SearchResult:
    base: dict[str, object] = {
        "id": "segment-1",
        "video_id": "video-1",
        "granularity": "segment",
        "ts_start_s": 10.0,
        "ts_end_s": 15.0,
        "score": 0.049,
        "thumbnail_url": "https://minio.local/derived/thumb.jpg",
    }
    base.update(overrides)
    return SearchResult(**base)  # type: ignore[arg-type]


# --- filters -----------------------------------------------------------------


def test_empty_lists_collapse_to_no_constraint() -> None:
    # filters_applied drives the removable chips in the UI. Keeping [] would
    # claim a constraint that was never evaluated, so the user would see a chip
    # they cannot account for.
    filters = SearchFilters(weather=[], objects_any=[], behaviors=[])
    assert filters.weather is None
    assert filters.objects_any is None
    assert filters.behaviors is None


def test_has_constraints_distinguishes_empty_from_set() -> None:
    assert SearchFilters().has_constraints is False
    assert SearchFilters(weather=[]).has_constraints is False
    assert SearchFilters(weather=["rainy"]).has_constraints is True


def test_zero_minimum_object_count_is_rejected() -> None:
    # "At least zero pedestrians" is satisfied by every frame, so it is never
    # what the caller meant.
    with pytest.raises(ValidationError, match="at least 1"):
        SearchFilters(min_object_counts={"person": 0})


def test_reversed_time_range_is_a_request_error() -> None:
    # Validated at the edge so the Qdrant filter builder's ValueError can never
    # be reached from a request: this is a 422, not a 500.
    with pytest.raises(ValidationError, match="after end"):
        SearchFilters(time_range_s=(30.0, 10.0))


def test_negative_time_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SearchFilters(time_range_s=(-1.0, 10.0))


def test_equal_start_and_end_is_a_valid_instant() -> None:
    # A frame has ts_start_s == ts_end_s, so an instant query must be expressible.
    assert SearchFilters(time_range_s=(10.0, 10.0)).time_range_s == (10.0, 10.0)


# --- request -----------------------------------------------------------------


def test_defaults_are_the_ones_the_ui_relies_on() -> None:
    request = SearchRequest(query="trời mưa")
    assert request.granularity == "segment"
    assert request.limit == 20
    assert request.cursor is None
    assert request.rerank is False
    assert request.explain is False
    assert request.filters.has_constraints is False


def test_vietnamese_query_survives_intact() -> None:
    # The headline demo query. Any normalisation that mangles diacritics would
    # change what the LLM sees and what gets cached.
    text = "trời mưa, có người đi bộ băng qua trước xe"
    assert SearchRequest(query=text).query == text


def test_blank_query_is_rejected() -> None:
    # str_strip_whitespace runs before the length check, so "   " is empty.
    with pytest.raises(ValidationError):
        SearchRequest(query="   ")


def test_query_and_limit_are_bounded() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="x" * (MAX_QUERY_LENGTH + 1))
    with pytest.raises(ValidationError):
        SearchRequest(query="ok", limit=MAX_LIMIT + 1)
    with pytest.raises(ValidationError):
        SearchRequest(query="ok", limit=0)


def test_unknown_granularity_is_rejected() -> None:
    # Both granularities share one Qdrant collection and are separated only by
    # this field; an unrecognised value would silently match nothing.
    with pytest.raises(ValidationError):
        SearchRequest(query="ok", granularity="clip")  # type: ignore[arg-type]


# --- result ------------------------------------------------------------------


def test_fused_score_is_not_bounded_like_a_similarity() -> None:
    # RRF sums 1/(60 + rank) across signals. It is not a similarity and does not
    # live in [0, 1]; bounding it would force a normalisation that exists only
    # to satisfy the schema.
    assert _result(score=2.5).score == 2.5


def test_negative_score_is_still_rejected() -> None:
    with pytest.raises(ValidationError):
        _result(score=-0.1)


def test_end_before_start_is_rejected() -> None:
    with pytest.raises(ValidationError, match="before ts_start_s"):
        _result(ts_start_s=15.0, ts_end_s=10.0)


def test_a_frame_may_have_zero_duration() -> None:
    assert _result(ts_start_s=10.0, ts_end_s=10.0).granularity == "segment"


def test_media_urls_are_both_optional() -> None:
    # A null preview means "not yet playable", not "no video". A null thumbnail
    # means the same: the keyframe is indexed but its derived image has not been
    # produced, which is true of a large part of the current corpus. Requiring one
    # would mean dropping those results from search entirely.
    #
    # What must never happen is either field carrying a URL to an original, and
    # that is enforced by the store an object lives in (ADR-0003), not here.
    assert _result().preview_url is None
    bare = SearchResult(
        id="s1",
        video_id="v1",
        granularity="segment",
        ts_start_s=0.0,
        ts_end_s=1.0,
        score=0.1,
    )
    assert bare.thumbnail_url is None
    assert bare.preview_url is None


# --- response ----------------------------------------------------------------


def test_response_round_trips_through_json() -> None:
    # The UI consumes this over HTTP, so the serialised form is the contract.
    response = SearchResponse(
        query="trời mưa",
        filters_applied=SearchFilters(weather=["rainy"], objects_any=["person"]),
        results=[_result(score_breakdown={"dense": 0.02, "behavior": 0.016})],
        total=1,
        next_cursor="eyJvIjoyMH0",
        took_ms=182.4,
        model_version="siglip-b16-224-v1",
    )
    restored = SearchResponse.model_validate_json(response.model_dump_json())

    assert restored.filters_applied.weather == ["rainy"]
    assert restored.results[0].score_breakdown == {"dense": 0.02, "behavior": 0.016}
    assert restored.model_version == "siglip-b16-224-v1"


def test_empty_response_is_valid() -> None:
    # No results is a normal outcome, especially while attribute filters have
    # nothing to match against. It must not require special-casing.
    response = SearchResponse(query="x", total=0, took_ms=12.0, model_version="v1")
    assert response.results == []
    assert response.next_cursor is None


# --- drift -------------------------------------------------------------------


def test_granularity_matches_the_retrieval_layer() -> None:
    # Duplicated rather than imported, to keep contracts independent of the
    # retrieval implementation. This test is what makes the duplication safe.
    from typing import get_args

    from schemas.search import Granularity as SchemaGranularity
    from search.points import Granularity as PointsGranularity

    assert set(get_args(SchemaGranularity)) == set(get_args(PointsGranularity))


def test_every_filter_field_has_a_qdrant_payload_index() -> None:
    # A filter without a payload index does not fail -- it degrades to a full
    # collection scan. Adding a field here without adding the index is the
    # silent version of a performance bug.
    from infrastructure.qdrant import _PAYLOAD_INDEXES

    indexed = set(_PAYLOAD_INDEXES)
    field_to_payload = {
        "dataset": "dataset",
        "video_ids": "video_id",
        "weather": "weather",
        "timeofday": "timeofday",
        "scene": "scene",
        "objects_any": "objects",
        "objects_all": "objects",
        "min_object_counts": "objects",
        "behaviors": "behaviors",
        "time_range_s": "ts_start_s",
    }
    assert set(SearchFilters.model_fields) == set(field_to_payload)
    assert set(field_to_payload.values()) <= indexed
