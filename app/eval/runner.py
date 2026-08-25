"""Run a query suite against a search engine and produce a report.

The runner's job is mostly refusal. Anything it cannot measure defensibly it marks
``UNAVAILABLE`` and explains, rather than emitting a number that would be quoted
later without its caveat. Three things it will not do:

* score a band whose ground truth came from the same captions the search read
  (FR-EVAL-06 — enforced by :func:`eval.truth.check_independence`);
* report metrics when the ground-truth join covered too little of the results to
  mean anything — a broken video-id join produces zeros that read exactly like
  catastrophic retrieval;
* average a missing value in as zero.

Ablations (FR-EVAL-04) are the variants that *exist*. The SRS names five: ±filters,
±prompt expansion, ±dedup, ±rerank, and frame vs segment. Only two of those are
real on this system today — strict concept filtering, and the similarity floor —
plus the tower split, which is the more informative comparison anyway. The rest
are listed in the report as not applicable with the reason, because a table with
silent gaps invites the reader to assume they were zero.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from eval import metrics as M
from eval.suite import BANDS, QueryCase, default_suite
from eval.truth import (
    CircularEvaluationError,
    GroundTruth,
    GroundTruthUnavailable,
    Judgement,
    ResultRef,
    Source,
    check_independence,
)

# The cutoffs FR-EVAL-02 names.
PRECISION_CUTOFFS = (5, 10)
RECALL_CUTOFF = 50
NDCG_CUTOFF = 10

# Results requested per query. Has to be at least the recall cutoff or recall@50
# is measuring a page of 20.
DEFAULT_LIMIT = RECALL_CUTOFF


class Engine(Protocol):
    async def search(self, query: str, **kwargs: Any) -> Any: ...


@dataclass
class CaseResult:
    """One query's outcome. ``status`` decides whether the numbers are usable."""

    case_id: str
    band: str
    query: str
    status: str  # "scored" | "unavailable" | "control_pass" | "control_fail" | "error"
    reason: str = ""

    took_ms: float = 0.0
    returned: int = 0
    exhaustive: bool = False
    below_threshold: bool = False
    signals_used: tuple[str, ...] = ()

    precision_at_5: float = float("nan")
    precision_at_10: float = float("nan")
    precision_of_shown: float = float("nan")
    recall_at_50: float = float("nan")
    ndcg_at_10: float = float("nan")
    reciprocal_rank: float = float("nan")

    # Diagnostics that separate "did not find the clip" from "found the clip and
    # surfaced the wrong moment in it".
    ideal_videos: int = 0
    video_level_hits: int = 0
    keyframe_misses: int = 0
    unjudged: int = 0
    exhaustive_denominator: bool = True

    @property
    def is_scored(self) -> bool:
        return self.status == "scored"


@dataclass
class BandSummary:
    band: str
    scored: int
    unavailable: int
    reason: str = ""
    precision_at_5: float = float("nan")
    precision_at_10: float = float("nan")
    recall_at_50: float = float("nan")
    ndcg_at_10: float = float("nan")
    mrr: float = float("nan")

    @property
    def is_available(self) -> bool:
        return self.scored > 0


@dataclass
class Report:
    cases: list[CaseResult] = field(default_factory=list)
    bands: list[BandSummary] = field(default_factory=list)
    latency_p50_ms: float = float("nan")
    latency_p95_ms: float = float("nan")
    controls_passed: int = 0
    controls_failed: int = 0
    join_rate: float = float("nan")
    corpus_videos: int = 0
    corpus_keyframes: int = 0
    label: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def overall_precision_at_10(self) -> float:
        return M.mean([c.precision_at_10 for c in self.cases if c.is_scored])


def _results_of(outcome: Any) -> list[ResultRef]:
    refs: list[ResultRef] = []
    for match in getattr(outcome, "matches", ()):  # noqa: B009
        keyframe = match.keyframe
        refs.append(
            ResultRef(
                video_id=keyframe.video_id,
                frame_no=int(getattr(keyframe, "frame_no", -1) or -1),
                point_id=getattr(keyframe, "point_id", ""),
            )
        )
    return refs


def _score(case: QueryCase, judgement: Judgement, ranked: Sequence[str]) -> dict[str, float]:
    relevant = judgement.relevant
    p5 = M.precision_at_k(ranked, relevant, 5)
    p10 = M.precision_at_k(ranked, relevant, 10)
    return {
        "precision_at_5": p5.value,
        "precision_at_10": p10.value,
        "precision_of_shown": p10.of_shown,
        "recall_at_50": M.recall_at_k(ranked, judgement.ideal_videos, RECALL_CUTOFF),
        "ndcg_at_10": M.ndcg_at_k(ranked, relevant, NDCG_CUTOFF),
        "reciprocal_rank": M.reciprocal_rank(ranked, relevant),
    }


async def run_case(
    engine: Engine,
    case: QueryCase,
    truth: GroundTruth | None,
    *,
    limit: int = DEFAULT_LIMIT,
    search_kwargs: dict[str, Any] | None = None,
) -> CaseResult:
    result = CaseResult(case_id=case.id, band=case.band, query=case.query, status="error")

    started = time.perf_counter()
    try:
        outcome = await engine.search(case.query, limit=limit, **(search_kwargs or {}))
    except Exception as exc:  # a query that raises is a finding, not a crash
        result.reason = f"{type(exc).__name__}: {exc}"
        result.took_ms = (time.perf_counter() - started) * 1000.0
        return result
    result.took_ms = (time.perf_counter() - started) * 1000.0

    refs = _results_of(outcome)
    result.returned = len(refs)
    result.exhaustive = bool(getattr(outcome, "exhaustive", False))
    result.below_threshold = bool(getattr(outcome, "below_threshold", False))
    result.signals_used = tuple(getattr(outcome, "signals_used", ()))

    # Abstention controls are pass/fail. Ranked metrics on a query with no correct
    # answer are meaningless; what matters is whether anything came back at all.
    if case.expect_empty:
        result.status = "control_pass" if not refs else "control_fail"
        if refs:
            result.reason = (
                f"returned {len(refs)} result(s) for a query the corpus cannot answer; "
                "the similarity floor did not reject it"
            )
        return result

    if truth is None or case.truth_source is Source.CAPTIONS:
        result.status = "unavailable"
        result.reason = (
            case.note or "no ground truth independent of the captions the search reads (FR-EVAL-06)"
        )
        return result

    try:
        check_independence(truth, result.signals_used, query_id=case.id)
        judgement = truth.judge(case.id, refs)
    except CircularEvaluationError as exc:
        result.status = "unavailable"
        result.reason = str(exc)
        return result
    except GroundTruthUnavailable as exc:
        result.status = "unavailable"
        result.reason = str(exc)
        return result

    ranked = [ref.video_id for ref in refs]
    for name, value in _score(case, judgement, ranked).items():
        setattr(result, name, value)

    result.ideal_videos = len(judgement.ideal_videos)
    result.video_level_hits = len(judgement.video_level_hits)
    result.keyframe_misses = judgement.keyframe_precision_loss
    result.unjudged = len(judgement.unjudged)
    result.exhaustive_denominator = judgement.exhaustive_denominator
    result.status = "scored"
    return result


async def run_suite(
    engine: Engine,
    *,
    truth_for: dict[str, GroundTruth | None],
    cases: Sequence[QueryCase] | None = None,
    limit: int = DEFAULT_LIMIT,
    search_kwargs: dict[str, Any] | None = None,
    label: str = "",
) -> Report:
    """Run every case and summarise per band.

    ``truth_for`` maps a band name to its ground truth, or to ``None`` when that
    band has none — which is a legitimate configuration, not an error.
    """

    suite = tuple(cases) if cases is not None else default_suite()
    report = Report(label=label)

    for case in suite:
        outcome = await run_case(
            engine,
            case,
            truth_for.get(case.band),
            limit=limit,
            search_kwargs=search_kwargs,
        )
        report.cases.append(outcome)

    latencies = [c.took_ms for c in report.cases if c.status != "error"]
    report.latency_p50_ms = M.percentile(latencies, 0.50)
    report.latency_p95_ms = M.percentile(latencies, 0.95)
    report.controls_passed = sum(1 for c in report.cases if c.status == "control_pass")
    report.controls_failed = sum(1 for c in report.cases if c.status == "control_fail")

    for band in BANDS:
        in_band = [c for c in report.cases if c.band == band and not _is_control(c, suite)]
        if not in_band:
            continue
        scored = [c for c in in_band if c.is_scored]
        unavailable = [c for c in in_band if c.status == "unavailable"]
        report.bands.append(
            BandSummary(
                band=band,
                scored=len(scored),
                unavailable=len(unavailable),
                reason=unavailable[0].reason if unavailable and not scored else "",
                precision_at_5=M.mean([c.precision_at_5 for c in scored]),
                precision_at_10=M.mean([c.precision_at_10 for c in scored]),
                recall_at_50=M.mean([c.recall_at_50 for c in scored]),
                ndcg_at_10=M.mean([c.ndcg_at_10 for c in scored]),
                mrr=M.mean([c.reciprocal_rank for c in scored]),
            )
        )

    judged = sum(c.returned for c in report.cases if c.is_scored)
    unjudged = sum(c.unjudged for c in report.cases if c.is_scored)
    if judged:
        report.join_rate = (judged - unjudged) / judged

    return report


def _is_control(result: CaseResult, suite: Sequence[QueryCase]) -> bool:
    return any(case.id == result.case_id and case.expect_empty for case in suite)


# -- ablations ----------------------------------------------------------------

# FR-EVAL-04's list, mapped onto what this system actually has. The entries that
# do not exist are carried so the report can say why rather than omitting a row.
ABLATIONS: tuple[tuple[str, dict[str, Any] | None, str], ...] = (
    ("baseline", {}, "hybrid retrieval as shipped"),
    ("visual only", {"mode": "visual"}, "the SigLIP tower alone, no caption evidence"),
    ("caption only", {"mode": "caption"}, "caption signals alone, no image similarity"),
    (
        "no strict concepts",
        {"strict": False},
        "a named concept becomes a preference rather than a hard filter",
    ),
    (
        "no similarity floor",
        {"min_score": 0.0},
        "only meaningful together with SEARCH_VISUAL_FLOOR=0 in the environment",
    ),
    ("prompt expansion", None, "not applicable — no query expansion exists"),
    ("rerank", None, "not applicable — no reranker exists"),
    (
        "frame vs segment",
        None,
        "not applicable — the attached index stores keyframes only, no segments",
    ),
)


async def run_ablations(
    engine: Engine,
    *,
    truth_for: dict[str, GroundTruth | None],
    cases: Sequence[QueryCase] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[tuple[str, str, Report | None]]:
    """Run the suite once per applicable variant. Returns ``(name, note, report)``."""

    out: list[tuple[str, str, Report | None]] = []
    for name, kwargs, note in ABLATIONS:
        if kwargs is None:
            out.append((name, note, None))
            continue
        report = await run_suite(
            engine,
            truth_for=truth_for,
            cases=cases,
            limit=limit,
            search_kwargs=kwargs,
            label=name,
        )
        out.append((name, note, report))
    return out


__all__ = [
    "ABLATIONS",
    "DEFAULT_LIMIT",
    "NDCG_CUTOFF",
    "PRECISION_CUTOFFS",
    "RECALL_CUTOFF",
    "BandSummary",
    "CaseResult",
    "Engine",
    "Report",
    "run_ablations",
    "run_case",
    "run_suite",
]
