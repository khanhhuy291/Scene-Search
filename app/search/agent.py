"""Tri-Tier Adaptive Agentic Search Orchestrator for driving scene retrieval."""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.config import get_settings
from search.evaluator import EvaluationVerdict, get_retrieval_evaluator
from search.query import ParsedQuery
from search.router import DomainVerdict, SearchRoute, get_unified_router


@dataclass(frozen=True)
class AgenticExecutionTrace:
    route: SearchRoute
    domain_verdict: DomainVerdict
    route_reason: str
    hyde_caption: str | None = None
    reflection_loops: int = 0
    relaxed: bool = False


class TriTierAgentOrchestrator:
    """Orchestrates Domain Guardrails, Visual-HyDE, Hybrid Retrieval, and Reflection Loops."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._router = get_unified_router()
        self._evaluator = get_retrieval_evaluator()

    async def execute(
        self,
        raw_query: str,
        parsed: ParsedQuery,
        *,
        retrieval_executor: Callable[
            [ParsedQuery, str | None, list[str]], Coroutine[Any, Any, Any]
        ],
    ) -> tuple[Any, AgenticExecutionTrace]:
        """Execute the tri-tier agentic search workflow."""
        start_time = time.perf_counter()
        tuning = self._settings.search

        # -------------------------------------------------------------
        # TIER 1 & 2: SINGLE-PASS DOMAIN GUARDRAIL, INTENT & VISUAL-HyDE
        # -------------------------------------------------------------
        analysis = await self._router.analyze(raw_query, parsed)
        logger.info(
            "Tri-Tier Unified Analysis: route={} domain={} reason={}",
            analysis.route.value,
            analysis.domain_verdict.value,
            analysis.reason,
        )

        signals_used: list[str] = [f"route:{analysis.route.value}"]

        # Guardrail immediate exit for clear out-of-domain queries
        if analysis.route == SearchRoute.REJECT_OOD:
            from search.engine import SearchOutcome

            took_ms = (time.perf_counter() - start_time) * 1000
            empty_outcome = SearchOutcome(
                parsed=parsed,
                matches=(),
                total_videos=0,
                total_keyframes=0,
                exhaustive=False,
                signals_used=("domain_guardrail",),
                next_cursor=None,
                took_ms=took_ms,
                similarity_floor=tuning.visual_floor,
                below_threshold=True,
                unconfirmed_concepts=(),
                degraded=False,
            )
            trace = AgenticExecutionTrace(
                route=analysis.route,
                domain_verdict=analysis.domain_verdict,
                route_reason=analysis.reason,
                hyde_caption=None,
                reflection_loops=0,
                relaxed=False,
            )
            return empty_outcome, trace

        hyde_caption = analysis.visual_hyde_caption
        if hyde_caption:
            signals_used.append("visual_hyde")

        # -------------------------------------------------------------
        # TIER 3: RETRIEVAL & ADAPTIVE REFLECTION LOOP
        # -------------------------------------------------------------
        current_parsed = parsed
        if analysis.english_query:
            from dataclasses import replace

            current_parsed = replace(current_parsed, semantic_text=analysis.english_query)
        reflection_loops = 0
        relaxed = False

        outcome = await retrieval_executor(current_parsed, hyde_caption, signals_used)

        max_loops = tuning.max_reflection_loops
        if tuning.agentic_enabled and max_loops > 0:
            eval_report = self._evaluator.evaluate(
                raw_matches_count=len(outcome.matches),
                total_videos=outcome.total_videos,
                below_threshold=outcome.below_threshold,
                parsed=current_parsed,
                retry_count=reflection_loops,
                max_loops=max_loops,
            )

            if (
                eval_report.verdict == EvaluationVerdict.NEEDS_RELAXATION
                and eval_report.relaxed_parsed
            ):
                reflection_loops += 1
                relaxed = True
                signals_used.append("adaptive_relaxation")
                current_parsed = eval_report.relaxed_parsed

                logger.info(
                    "Executing adaptive reflection retry #{} with relaxed constraints",
                    reflection_loops,
                )
                outcome = await retrieval_executor(current_parsed, hyde_caption, signals_used)

        trace = AgenticExecutionTrace(
            route=analysis.route,
            domain_verdict=analysis.domain_verdict,
            route_reason=analysis.reason,
            hyde_caption=hyde_caption,
            reflection_loops=reflection_loops,
            relaxed=relaxed,
        )

        return outcome, trace


_agent_orchestrator: TriTierAgentOrchestrator | None = None


def get_agent_orchestrator() -> TriTierAgentOrchestrator:
    """Return process-singleton TriTierAgentOrchestrator."""
    global _agent_orchestrator
    if _agent_orchestrator is None:
        _agent_orchestrator = TriTierAgentOrchestrator()
    return _agent_orchestrator
