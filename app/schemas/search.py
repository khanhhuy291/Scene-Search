"""Vector search contracts shared by the API, UI and saved review sessions.

Only explicit request filters constrain Qdrant retrieval. Legacy response fields
for concept inference remain empty for compatibility with existing exports.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Kept in step with ``search.points.Granularity`` by a test rather than by an
# import: contracts should not depend on the retrieval implementation, and a
# two-value literal is cheaper to duplicate than to invert the layering for.
Granularity = Literal["frame", "segment"]

# hybrid combines siglip and qwen rankings with equal-weight RRF (k=60).
SearchMode = Literal["siglip", "qwen", "hybrid"]

MAX_QUERY_LENGTH = 1000
MAX_LIMIT = 100


class SearchFilters(BaseModel):
    """Explicit structured constraints applied inside Qdrant.

    Every field maps to a Qdrant payload field with a payload index behind it, so
    all of these are evaluated *inside* the vector search rather than applied to
    its output. Adding a field here without adding the matching payload index
    turns that filter into a full collection scan.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    dataset: list[str] | None = None
    video_ids: list[str] | None = None

    # Attribute bands. On the current corpus these arrive from the offline
    # enrichment pass rather than from dataset labels, so they may be absent for
    # a while -- a filter on them will match nothing rather than error.
    weather: list[str] | None = None
    timeofday: list[str] | None = None
    scene: list[str] | None = None

    # ``objects_any`` is "contains at least one of"; ``objects_all`` is
    # "contains every one of". Qdrant's keyword match on an array is
    # contains-any, so the conjunction becomes one condition per class.
    objects_any: list[str] | None = None
    objects_all: list[str] | None = None
    min_object_counts: dict[str, int] | None = None

    behaviors: list[str] | None = None

    # Inclusive, and matched on overlap rather than containment: a segment that
    # spans the requested window matches even if it starts before or ends after.
    time_range_s: tuple[float, float] | None = None

    @field_validator(
        "dataset",
        "video_ids",
        "weather",
        "timeofday",
        "scene",
        "objects_any",
        "objects_all",
        "behaviors",
        mode="after",
    )
    @classmethod
    def _empty_list_means_no_constraint(cls, value: list[str] | None) -> list[str] | None:
        return value or None

    @field_validator("min_object_counts", mode="after")
    @classmethod
    def _counts_must_be_positive(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if not value:
            return None
        for class_name, count in value.items():
            # A minimum of zero is satisfied by everything, so it is never what
            # the caller meant; silently keeping it would produce a chip the user
            # cannot make sense of.
            if count < 1:
                raise ValueError(
                    f"min_object_counts[{class_name!r}] must be at least 1, got {count}"
                )
        return value

    @model_validator(mode="after")
    def _time_range_is_ordered(self) -> SearchFilters:
        # Validated at the edge so the filter builder's ValueError can never be
        # reached from a request: a malformed range is a 422, not a 500.
        if self.time_range_s is not None:
            start, end = self.time_range_s
            if start > end:
                raise ValueError(f"time_range_s start {start} is after end {end}")
            if start < 0:
                raise ValueError(f"time_range_s start must not be negative, got {start}")
        return self

    @property
    def has_constraints(self) -> bool:
        """True when at least one filter is set.

        Lets callers check whether the user supplied any constraints.
        """

        return any(value is not None for value in self.model_dump().values())


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    filters: SearchFilters = Field(default_factory=SearchFilters)

    # Frames answer "which instant"; segments answer "which few seconds should I
    # watch". Both live in one collection. None searches across both.
    granularity: Granularity | None = None

    limit: int = Field(default=20, ge=1, le=MAX_LIMIT)

    # Opaque, and deliberately not an offset. Offset paging over an ANN search
    # re-runs the traversal and can return the same point on two pages.
    cursor: str | None = Field(default=None, max_length=2048)

    # Optional cutoff on each tower cosine score, before RRF. Zero disables it.
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Which towers to query. If None, falls back to SEARCH_MODE from configuration.
    mode: SearchMode | None = None

    explain: bool = False


class SearchResult(BaseModel):
    """One ranked frame or segment, ready to render."""

    id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    granularity: Granularity

    ts_start_s: float = Field(ge=0.0)
    ts_end_s: float = Field(ge=0.0)

    # Raw cosine for a single tower; RRF score for hybrid.
    score: float = Field(ge=-1.0, allow_inf_nan=False)

    thumbnail_url: str | None = None
    preview_url: str | None = None

    objects: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)

    caption: str | None = None
    frame_no: int | None = Field(default=None, ge=0)

    keyframes_matched: int = Field(default=1, ge=1)
    keyframes_in_video: int = Field(default=0, ge=0)
    contradicting_moments: int = Field(default=0, ge=0)

    confirmed: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    matched_moments: list[dict[str, Any]] = Field(default_factory=list)

    score_breakdown: dict[str, float] | None = None

    video_second: float | None = None
    weather: str | None = None
    time_of_day: str | None = None
    scene_type: str | None = None
    retrieval_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _end_must_follow_start(self) -> SearchResult:
        if self.ts_end_s < self.ts_start_s:
            raise ValueError(f"ts_end_s {self.ts_end_s} is before ts_start_s {self.ts_start_s}")
        return self


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode = "hybrid"
    filters_applied: SearchFilters = Field(default_factory=SearchFilters)

    results: list[SearchResult] = Field(default_factory=list)

    total: int = Field(ge=0)
    total_keyframes: int = Field(default=0, ge=0)

    interpreted_query: str = ""
    required_concepts: list[str] = Field(default_factory=list)
    excluded_concepts: list[str] = Field(default_factory=list)
    unmatched_terms: list[str] = Field(default_factory=list)

    exhaustive: bool = False
    signals_used: list[str] = Field(default_factory=list)

    similarity_floor: float = Field(default=0.0, ge=0.0, le=1.0)
    below_threshold: bool = False
    unconfirmed_concepts: list[str] = Field(default_factory=list)
    degraded: bool = False

    next_cursor: str | None = None
    took_ms: float = Field(ge=0.0)

    model_version: str


__all__ = [
    "Granularity",
    "MAX_LIMIT",
    "MAX_QUERY_LENGTH",
    "SearchFilters",
    "SearchMode",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
]
