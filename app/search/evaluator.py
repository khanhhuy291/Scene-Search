"""Retrieval outcome evaluator and adaptive constraint relaxation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

from search.query import ParsedQuery


class EvaluationVerdict(StrEnum):
    SATISFIED = "satisfied"
    NEEDS_RELAXATION = "needs_relaxation"
    OUT_OF_DOMAIN_OR_EMPTY = "out_of_domain_or_empty"


@dataclass(frozen=True)
class EvaluationReport:
    verdict: EvaluationVerdict
    reason: str
    relaxed_query: str | None = None
    relaxed_parsed: ParsedQuery | None = None


class RetrievalEvaluator:
    """Evaluates search results and decides whether to relax constraints and retry."""

    def evaluate(
        self,
        raw_matches_count: int,
        total_videos: int,
        below_threshold: bool,
        parsed: ParsedQuery,
        retry_count: int,
        max_loops: int = 1,
    ) -> EvaluationReport:
        """Analyze search outcome to decide if reflection/relaxation is needed."""
        # 1. If we already have good results (>= 2 videos) and not below floor, we are satisfied.
        if total_videos >= 2 and not below_threshold:
            return EvaluationReport(
                verdict=EvaluationVerdict.SATISFIED,
                reason=f"Found {total_videos} matching videos satisfying all constraints",
            )

        # 2. If single top result exists with clear confidence
        if total_videos == 1 and not below_threshold:
            return EvaluationReport(
                verdict=EvaluationVerdict.SATISFIED,
                reason="Found high-confidence single video match",
            )

        # 4. If query had multiple explicit exclusions (> 1) that produced 0 results,
        # we attempt to relax secondary exclusions to recover candidate videos
        if len(parsed.excluded) > 1 and total_videos == 0:
            relaxed_excluded = tuple(list(parsed.excluded)[:1])
            relaxed_required = tuple(parsed.required)

            relaxed_parsed = ParsedQuery(
                raw=parsed.raw,
                semantic_text=parsed.semantic_text,
                required=relaxed_required,
                excluded=relaxed_excluded,
                unmatched_exclusions=parsed.unmatched_exclusions,
            )

            logger.info(
                "Adaptive relaxation triggered: relaxing exclusions {} -> {}",
                list(parsed.excluded),
                list(relaxed_excluded),
            )

            return EvaluationReport(
                verdict=EvaluationVerdict.NEEDS_RELAXATION,
                reason="Relaxed non-primary exclusions to recover candidate videos",
                relaxed_query=parsed.semantic_text,
                relaxed_parsed=relaxed_parsed,
            )

        return EvaluationReport(
            verdict=EvaluationVerdict.OUT_OF_DOMAIN_OR_EMPTY,
            reason="No matching footage found in corpus above visual floor",
        )


_evaluator: RetrievalEvaluator | None = None


def get_retrieval_evaluator() -> RetrievalEvaluator:
    """Return process-singleton RetrievalEvaluator."""
    global _evaluator
    if _evaluator is None:
        _evaluator = RetrievalEvaluator()
    return _evaluator
