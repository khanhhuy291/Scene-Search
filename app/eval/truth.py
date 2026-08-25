"""Ground truth, and the guard that stops it being circular.

The rule this module enforces is SRS FR-EVAL-06: *the harness shall not use
VLM-generated metadata as ground truth for queries answered by that same
VLM-generated metadata.* It is written as a rule because the violation is
invisible in the output — scoring caption-based retrieval against caption-derived
labels yields precision near 1.0, which looks like success and means the model
agreed with itself.

So the guard is in code, not in a comment. Every :class:`GroundTruth` declares its
:class:`Source`, every search result records which signals produced it, and
:func:`check_independence` refuses the combination. It raises by default. A band
that cannot be judged independently is reported ``UNAVAILABLE`` — never scored,
never silently zero.

**Relevance is judged on the returned keyframe, not the video.** The system
returns one moment per video and the user clicks that moment. A video that
contains a qualifying frame somewhere, represented by a keyframe that does not
qualify, is a miss — because what was shown was wrong. The recall denominator is
still videos-with-a-qualifying-frame, so :class:`Judgement` also carries the
video-level hit set: comparing the two says whether a miss was "never found the
clip" or "found the clip, surfaced the wrong second", which are different bugs
with different owners.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Source(StrEnum):
    """Where a band's labels come from, and therefore what they can be used for."""

    MOT_TRACKS = "mot_tracks"
    HUMAN_JUDGEMENT = "human_judgement"
    FIXTURE = "fixture"
    # Present so it can be *refused*. Nothing should ever construct one of these
    # for a band the caption signal answers; it exists to make the refusal
    # expressible rather than theoretical.
    CAPTIONS = "captions"


# Retrieval signals that read the VLM captions. A ground truth derived from those
# same captions cannot judge a result these produced.
CAPTION_DERIVED_SIGNALS = frozenset({"caption_text", "caption_vector"})


class CircularEvaluationError(RuntimeError):
    """Ground truth and retrieval share a source, so the score would be a tautology."""


class GroundTruthUnavailable(RuntimeError):
    """The source this band needs is not present. The band is not scored."""


@dataclass(frozen=True)
class ResultRef:
    """The part of a search result that ground truth can be evaluated against."""

    video_id: str
    frame_no: int
    point_id: str = ""


@dataclass(frozen=True)
class Judgement:
    """Which results were right, and how much of the corpus should have been found."""

    relevant: frozenset[str]
    # Videos that contain at least one qualifying frame. The recall denominator.
    ideal_videos: frozenset[str]
    # Videos that were returned and do contain a qualifying frame *somewhere*,
    # whether or not the surfaced keyframe was the qualifying one.
    video_level_hits: frozenset[str] = frozenset()
    # True when ``ideal_videos`` is every qualifying video in the corpus, false
    # when it is only what was pooled and judged. Recall means a weaker thing in
    # the second case and the report has to say which it is.
    exhaustive_denominator: bool = True
    # Results the truth source could say nothing about — an unmatched join, an
    # unjudged pool member. Counted, never guessed at.
    unjudged: frozenset[str] = frozenset()

    @property
    def keyframe_precision_loss(self) -> int:
        """Videos found but represented by a non-qualifying moment.

        Non-zero here is a keyframe-selection problem, not a retrieval problem.
        """

        return len(self.video_level_hits - self.relevant)


@runtime_checkable
class GroundTruth(Protocol):
    """Judges results for one query."""

    @property
    def source(self) -> Source: ...

    def judge(self, query_id: str, results: Sequence[ResultRef]) -> Judgement: ...


def check_independence(
    truth: GroundTruth, signals_used: Sequence[str], *, query_id: str = ""
) -> None:
    """Raise if the ground truth was derived from a signal that produced the results.

    Called once per query rather than once per run, because a suite can mix bands
    and only some of them are compromised.
    """

    if truth.source is not Source.CAPTIONS:
        return
    overlap = CAPTION_DERIVED_SIGNALS.intersection(signals_used)
    if overlap:
        raise CircularEvaluationError(
            f"query {query_id!r}: ground truth is caption-derived and the results "
            f"were produced by {', '.join(sorted(overlap))}. "
            "Scoring this measures the captioner agreeing with itself (FR-EVAL-06). "
            "Use MOT-derived or human ground truth, or report the band UNAVAILABLE."
        )


# -- object truth over MOT tracks --------------------------------------------

ObjectPredicate = Callable[[dict[str, int]], bool]


def at_least(class_name: str, count: int) -> ObjectPredicate:
    """ "at least N of this class in the frame" — the object band's workhorse."""

    def predicate(objects: dict[str, int]) -> bool:
        return objects.get(class_name, 0) >= count

    return predicate


def none_of(class_name: str) -> ObjectPredicate:
    def predicate(objects: dict[str, int]) -> bool:
        return objects.get(class_name, 0) == 0

    return predicate


def all_of(*predicates: ObjectPredicate) -> ObjectPredicate:
    def predicate(objects: dict[str, int]) -> bool:
        return all(inner(objects) for inner in predicates)

    return predicate


@dataclass
class MotGroundTruth:
    """Judges against object counts read from the MOT label table.

    Independent of the captions by construction, which is the entire point.
    """

    truth: object  # eval.mot.ObjectTruth
    predicates: dict[str, ObjectPredicate]
    frame_tolerance: int = 2
    _ideal_cache: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)

    @property
    def source(self) -> Source:
        return Source.MOT_TRACKS

    def ideal_videos(self, query_id: str) -> frozenset[str]:
        """Every video with at least one frame satisfying the predicate.

        Computed over the whole table, so the recall denominator is exhaustive
        rather than pooled — the strong form of the claim, and only possible
        because the label table covers every frame.
        """

        if query_id in self._ideal_cache:
            return self._ideal_cache[query_id]
        predicate = self._predicate(query_id)
        videos = {
            key.video_id
            for key, objects in self.truth.counts.items()  # type: ignore[attr-defined]
            if predicate(objects)
        }
        result = frozenset(videos)
        self._ideal_cache[query_id] = result
        return result

    def judge(self, query_id: str, results: Sequence[ResultRef]) -> Judgement:
        predicate = self._predicate(query_id)
        ideal = self.ideal_videos(query_id)

        relevant: set[str] = set()
        unjudged: set[str] = set()
        for result in results:
            objects = self.truth.at(  # type: ignore[attr-defined]
                result.video_id, result.frame_no, tolerance=self.frame_tolerance
            )
            if objects is None:
                unjudged.add(result.video_id)
                continue
            if predicate(objects):
                relevant.add(result.video_id)

        returned = {result.video_id for result in results}
        return Judgement(
            relevant=frozenset(relevant),
            ideal_videos=ideal,
            video_level_hits=frozenset(returned & ideal),
            exhaustive_denominator=True,
            unjudged=frozenset(unjudged),
        )

    def _predicate(self, query_id: str) -> ObjectPredicate:
        try:
            return self.predicates[query_id]
        except KeyError:
            raise GroundTruthUnavailable(
                f"no object predicate defined for query {query_id!r}"
            ) from None


# -- behaviour truth over MOT trajectories ------------------------------------


@dataclass
class BehaviorGroundTruth:
    """Judges behaviour queries against trajectories, not text.

    The behaviour rules in ``eval.behavior`` decide whether a
    pedestrian crossed the ego path by looking at where boxes move in the image
    plane. They never read a caption. That makes this band independent of the
    signal being evaluated, and it makes it the only place in the report where
    *"a pedestrian crossing in front of the car"* — the query the whole project is
    named for — gets a number instead of a demo.

    Expect that number to be low. The attached index has no behaviour tags, so
    caption retrieval has to infer a trajectory from a single frame's description.
    A low score here is a finding about the index, not a bug in the search.
    """

    events_by_video: dict[str, list[object]]
    kinds: dict[str, str]
    fps: float = 5.0
    # A keyframe counts if it falls inside the event, plus this margin either
    # side. The event is the crossing itself; a frame half a second before it is
    # still the moment a reviewer would want to watch.
    margin_s: float = 0.5

    @property
    def source(self) -> Source:
        return Source.MOT_TRACKS

    def _spans(self, query_id: str, video_id: str) -> list[tuple[float, float]]:
        kind = self.kinds.get(query_id)
        if kind is None:
            raise GroundTruthUnavailable(f"no behaviour kind defined for {query_id!r}")
        return [
            (event.ts_start_s - self.margin_s, event.ts_end_s + self.margin_s)  # type: ignore[attr-defined]
            for event in self.events_by_video.get(video_id, ())
            if event.kind == kind  # type: ignore[attr-defined]
        ]

    def ideal_videos(self, query_id: str) -> frozenset[str]:
        kind = self.kinds.get(query_id)
        if kind is None:
            raise GroundTruthUnavailable(f"no behaviour kind defined for {query_id!r}")
        return frozenset(
            video_id
            for video_id, events in self.events_by_video.items()
            if any(event.kind == kind for event in events)  # type: ignore[attr-defined]
        )

    def judge(self, query_id: str, results: Sequence[ResultRef]) -> Judgement:
        ideal = self.ideal_videos(query_id)
        relevant: set[str] = set()
        for result in results:
            if result.frame_no < 0:
                continue
            ts = result.frame_no / self.fps
            if any(start <= ts <= end for start, end in self._spans(query_id, result.video_id)):
                relevant.add(result.video_id)
        returned = {result.video_id for result in results}
        return Judgement(
            relevant=frozenset(relevant),
            ideal_videos=ideal,
            video_level_hits=frozenset(returned & ideal),
            exhaustive_denominator=True,
        )


# -- human judgement ----------------------------------------------------------


@dataclass
class HumanGroundTruth:
    """Judges against a filled-in judging pack.

    The denominator is the judged pool, not the corpus, so recall computed from
    this is "recall against what two people looked at". :class:`Judgement` carries
    ``exhaustive_denominator=False`` and the report is required to say so.
    """

    labels: dict[str, dict[str, bool]]

    @property
    def source(self) -> Source:
        return Source.HUMAN_JUDGEMENT

    def judge(self, query_id: str, results: Sequence[ResultRef]) -> Judgement:
        try:
            judged = self.labels[query_id]
        except KeyError:
            raise GroundTruthUnavailable(
                f"query {query_id!r} has no human labels; run the judging pack first"
            ) from None

        relevant = {video for video, is_relevant in judged.items() if is_relevant}
        unjudged = {r.video_id for r in results if r.video_id not in judged}
        return Judgement(
            relevant=frozenset(r.video_id for r in results if r.video_id in relevant),
            ideal_videos=frozenset(relevant),
            video_level_hits=frozenset({r.video_id for r in results} & relevant),
            exhaustive_denominator=False,
            unjudged=frozenset(unjudged),
        )


# -- fixtures -----------------------------------------------------------------


@dataclass
class FixtureGroundTruth:
    """Hand-written truth for the synthetic corpus the CI suite runs against.

    Marked as its own source so a fixture number can never be mistaken for a
    measurement of the real corpus.
    """

    relevant_by_query: dict[str, set[str]]

    @property
    def source(self) -> Source:
        return Source.FIXTURE

    def judge(self, query_id: str, results: Sequence[ResultRef]) -> Judgement:
        try:
            ideal = self.relevant_by_query[query_id]
        except KeyError:
            raise GroundTruthUnavailable(f"fixture truth missing for {query_id!r}") from None
        returned = {result.video_id for result in results}
        return Judgement(
            relevant=frozenset(returned & ideal),
            ideal_videos=frozenset(ideal),
            video_level_hits=frozenset(returned & ideal),
            exhaustive_denominator=True,
        )


__all__ = [
    "CAPTION_DERIVED_SIGNALS",
    "BehaviorGroundTruth",
    "CircularEvaluationError",
    "FixtureGroundTruth",
    "GroundTruth",
    "GroundTruthUnavailable",
    "HumanGroundTruth",
    "Judgement",
    "MotGroundTruth",
    "ObjectPredicate",
    "ResultRef",
    "Source",
    "all_of",
    "at_least",
    "check_independence",
    "none_of",
]
