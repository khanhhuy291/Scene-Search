"""Semantic scene-search request and response contracts.

These are consumed by the UI, by the review flow (a saved session stores the
query and the filters that produced it), and by the evaluation harness. Changing
them is a two-approval PR, because a field renamed here breaks three callers who
will each spend an hour finding out why.

Two conventions worth stating, because both are easy to get backwards:

``filters_applied`` on the response is not diagnostic output. It is the product
requirement that the engineer can see and correct what the system inferred from
their sentence, so it must carry the filters that were *actually applied* --
including ones the user never typed. The UI renders each entry as a removable
chip; a filter that is applied but not reported is a narrowed result set with no
visible cause and no way to widen it.

An empty list and ``None`` mean the same thing -- no constraint -- and are
normalised to ``None`` on the way in. Leaving ``[]`` in place would make
``filters_applied`` claim a constraint that was never evaluated.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Kept in step with ``search.points.Granularity`` by a test rather than by an
# import: contracts should not depend on the retrieval implementation, and a
# two-value literal is cheaper to duplicate than to invert the layering for.
Granularity = Literal["frame", "segment"]

# Which retrieval towers to run. Kept in step with ``search.engine.SearchMode``
# by a test rather than an import, for the same layering reason as ``Granularity``.
SearchMode = Literal["hybrid", "visual", "caption", "qwen", "siglip"]

MAX_QUERY_LENGTH = 1000
MAX_LIMIT = 100


class SearchFilters(BaseModel):
    """Structured constraints, whether typed by the user or inferred from text.

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

        Lets the search service skip building a filter object, and lets query
        understanding skip the LLM entirely when the sentence carried no cues.
        """

        return any(value is not None for value in self.model_dump().values())


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    filters: SearchFilters = Field(default_factory=SearchFilters)

    # Frames answer "which instant"; segments answer "which few seconds should I
    # watch". Both live in one collection. None searches across both.
    granularity: Granularity | None = None

    limit: int = Field(default=20, ge=1, le=MAX_LIMIT)

    # Opaque, and deliberately not an offset. Offset paging over an ANN search
    # re-runs the traversal and can return the same point on two pages.
    cursor: str | None = Field(default=None, max_length=2048)

    # Applies to the dense similarity in stage one, NOT to the fused score in
    # the response: those are different scales and comparing them is meaningless.
    #
    # Note for callers wiring a UI slider to this: SigLIP cosine similarities on
    # this corpus sit around 0.10-0.15, not the 0.7-0.9 a CLIP-shaped intuition
    # expects. A "75% similarity" cutoff returns nothing at all.
    #
    # This can only *tighten* the calibrated floor the service already applies
    # (``SEARCH_VISUAL_FLOOR``). Zero, the default, means "no cutoff beyond the
    # calibrated one" rather than "no cutoff"; the response echoes the floor that
    # was actually in force as ``similarity_floor``.
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Which towers to query. If None, falls back to SEARCH_MODE from configuration.
    mode: SearchMode | None = None

    # Overrides for what query understanding inferred. These are what make the
    # inferred filter chips removable, which is a product requirement rather than
    # a convenience: a filter that is applied but cannot be taken off is a
    # narrowed result set the user cannot widen. ``None`` means "use what was
    # inferred"; an empty list means "apply no constraint of this kind".
    require: list[str] | None = None
    exclude: list[str] | None = None

    rerank: bool | None = Field(default=None, description="Enable CrossEncoder candidate reranking")
    agentic: bool | None = Field(
        default=None, description="Enable Tri-Tier Adaptive Agentic Search loop"
    )
    explain: bool = False


class SearchResult(BaseModel):
    """One ranked frame or segment, ready to render."""

    id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    granularity: Granularity

    ts_start_s: float = Field(ge=0.0)
    ts_end_s: float = Field(ge=0.0)

    # The fused ranking score. Deliberately unbounded above: reciprocal rank
    # fusion sums 1/(60 + rank) across signals, which is not a similarity and
    # does not live in [0, 1]. Bounding it would force a normalisation whose only
    # purpose was to satisfy the schema.
    score: float = Field(ge=0.0)

    # Always the anonymized derivative. There is no code path that can produce a
    # URL for an original, and this field must never carry one.
    #
    # Nullable because a keyframe can be indexed before its derived thumbnail
    # exists, which is the current state of a large part of the corpus. Null means
    # "nothing to render yet" and the card falls back to the caption; it never
    # means "fall back to the original".
    thumbnail_url: str | None = None
    # Present once the video has an anonymized preview. The player seeks to
    # ``ts_start_s``; a null here means "not yet playable", not "no video".
    preview_url: str | None = None

    objects: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)

    # The keyframe's own description, from the offline vision-language pass. This
    # is what the user reads to judge a result, and on the current index it is the
    # only descriptive metadata that exists for every point.
    caption: str | None = None
    frame_no: int | None = Field(default=None, ge=0)

    # How many keyframes in this video satisfied the query, this one included.
    # One result per video keeps the grid readable; this is how the user learns
    # that a clip contains forty usable moments rather than one.
    keyframes_matched: int = Field(default=1, ge=1)
    # Every keyframe this video has in the index, matching or not. Without the
    # denominator "3 matching moments" is unreadable: 3 of 4 is a clip that is
    # mostly what you asked for, 3 of 40 is a clip that mostly is not.
    keyframes_in_video: int = Field(default=0, ge=0)
    # Moments elsewhere in the SAME clip whose caption positively shows something
    # the query excluded.
    #
    # This is the number that keeps a correct result from reading as a bug. A
    # search for "no pedestrians" returns the moment that has none; the clip it
    # came from is 40 seconds long and may well show a pedestrian later. A user
    # who is told that up front understands the tool. A user who discovers it by
    # watching concludes the search is broken.
    #
    # A LOWER BOUND, and the UI must phrase it as one: a caption that never
    # mentions people resolves to "unknown", not to absence, so this counts only
    # the moments a caption positively describes. "4 other moments mention
    # people" is accurate; "4 other moments contain people" is not.
    contradicting_moments: int = Field(default=0, ge=0)

    # Concepts the caption confirmed, and excluded concepts it explicitly
    # reported as absent. "Absent" is stronger evidence than silence: a caption
    # saying "no visible pedestrians" is a better answer to "without people" than
    # one that simply never mentions them.
    confirmed: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    # Matched keyframe moments in this video for interactive seeking.
    matched_moments: list[dict[str, Any]] = Field(default_factory=list)

    # Populated only when the request set ``explain``. Keys are signal names --
    # "dense", "metadata", "behavior" -- so a reviewer can see which signal
    # carried a result rather than inferring it.
    score_breakdown: dict[str, float] | None = None

    # Enriched metadata from payload
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
    # What was actually applied, inferred filters included. See the module
    # docstring: this drives the removable chips, it is not debug output.
    #
    # Empty on the current index, which carries no indexed attribute payload to
    # prefilter on. Attribute constraints are reported through
    # ``required_concepts`` / ``excluded_concepts`` instead, and are resolved from
    # captions. This field returns to use when the payload gains those fields.
    filters_applied: SearchFilters = Field(default_factory=SearchFilters)

    results: list[SearchResult] = Field(default_factory=list)

    # Videos matched, not keyframes -- results are one per video, so this is the
    # count the UI should show and the number that answers "how much footage is
    # there".
    total: int = Field(ge=0)
    total_keyframes: int = Field(default=0, ge=0)

    # The query after exclusion clauses were removed: this, not the raw sentence,
    # is what was embedded. Echoed back because a user who cannot see how their
    # sentence was read cannot tell a parsing problem from a relevance problem.
    interpreted_query: str = ""
    required_concepts: list[str] = Field(default_factory=list)
    excluded_concepts: list[str] = Field(default_factory=list)
    # Exclusion terms no concept covered. They were dropped from the semantic
    # query but could not be enforced, so saying so is the honest option.
    unmatched_terms: list[str] = Field(default_factory=list)

    # True when the result set is complete: every keyframe in the corpus was
    # checked against the query. False means these are the best of a large ranked
    # pool -- good answers, but not a guarantee that nothing was missed. It is the
    # difference between "these are the snowy videos" and "these look snowy".
    exhaustive: bool = False
    signals_used: list[str] = Field(default_factory=list)

    # The similarity cutoff that was in force, and why the answer may be empty.
    # An empty result has two very different causes and the UI must not phrase
    # them the same way: ``below_threshold`` means nothing in the corpus resembles
    # the query at all (the honest answer to "spiderman" over dashcam footage),
    # while ``unconfirmed_concepts`` names the required concepts that no caption
    # anywhere confirmed, which tells the user exactly which word to drop.
    similarity_floor: float = Field(default=0.0, ge=0.0, le=1.0)
    below_threshold: bool = False
    unconfirmed_concepts: list[str] = Field(default_factory=list)
    # A requested retrieval signal errored rather than returning nothing. When
    # true, treat every count below as a floor: this is a partial answer wearing
    # the same shape as a complete one.
    degraded: bool = False

    next_cursor: str | None = None
    took_ms: float = Field(ge=0.0)

    # Stamped so a saved review session, and any dataset exported from it, stays
    # interpretable after the encoder is swapped.
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
