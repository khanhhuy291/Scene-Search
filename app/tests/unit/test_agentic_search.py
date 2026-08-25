"""Unit tests for Tri-Tier Adaptive Agentic Search pipeline."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from core.config import get_settings
from search.agent import TriTierAgentOrchestrator
from search.evaluator import EvaluationVerdict, RetrievalEvaluator
from search.hyde import VisualHyDEGenerator
from search.llm_client import LLMClient
from search.query import parse_query
from search.router import DomainVerdict, SearchRoute, UnifiedAgentRouter


@pytest.fixture(autouse=True)
def enable_agentic_in_tests(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SEARCH_AGENTIC_ENABLED", "true")
    monkeypatch.setenv("SEARCH_HYDE_ENABLED", "true")
    monkeypatch.setenv("SEARCH_DOMAIN_GUARDRAIL_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_domain_guardrail_fast_rejects_out_of_domain_queries() -> None:
    router = UnifiedAgentRouter()

    for ood_query in [
        "spiderman in a city",
        "spider-man swinging",
        "công thức nấu phở ngon",
        "how to make pizza",
        "pikachu and pokemon",
        "solve quadratic equation in python",
    ]:
        parsed = parse_query(ood_query)
        decision = await router.analyze(ood_query, parsed)
        assert decision.route == SearchRoute.REJECT_OOD
        assert decision.domain_verdict == DomainVerdict.OUT_OF_DOMAIN
        assert decision.is_driving_scene is False


@pytest.mark.asyncio
async def test_llm_domain_guardrail_rejects_abstract_unrelated_queries() -> None:
    router = UnifiedAgentRouter()
    abstract_query = "tại sao giá vàng lại tăng đột biến hôm nay"

    llm_mock_response = json.dumps(
        {
            "is_driving_scene": False,
            "reason": "Economic / financial news inquiry unrelated to driving video footage",
            "is_complex": False,
            "visual_hyde_caption": None,
        }
    )

    with (
        patch.object(LLMClient, "is_available", True),
        patch.object(LLMClient, "complete", new_callable=AsyncMock) as mock_complete,
    ):
        mock_complete.return_value = llm_mock_response

        parsed = parse_query(abstract_query)
        decision = await router.analyze(abstract_query, parsed)

        assert decision.route == SearchRoute.REJECT_OOD
        assert decision.domain_verdict == DomainVerdict.OUT_OF_DOMAIN
        assert decision.is_driving_scene is False
        mock_complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_unified_router_generates_hyde_for_complex_driving_queries() -> None:
    router = UnifiedAgentRouter()
    complex_query = "xe ô tô rẽ trái bất ngờ suýt va chạm với người đi bộ"

    fake_hyde = (
        "Forward dashcam view on a wet urban intersection. "
        "A silver sedan executes a sharp left turn, narrowly yielding to a pedestrian."
    )
    llm_mock_response = json.dumps(
        {
            "is_driving_scene": True,
            "reason": "Realistic driving traffic scenario with turning vehicle and pedestrian",
            "is_complex": True,
            "visual_hyde_caption": fake_hyde,
        }
    )

    with (
        patch.object(LLMClient, "is_available", True),
        patch.object(LLMClient, "complete", new_callable=AsyncMock) as mock_complete,
    ):
        mock_complete.return_value = llm_mock_response

        parsed = parse_query(complex_query)
        decision = await router.analyze(complex_query, parsed)

        assert decision.route == SearchRoute.AGENTIC_PATH
        assert decision.domain_verdict == DomainVerdict.IN_DOMAIN
        assert decision.is_driving_scene is True
        assert decision.visual_hyde_caption == fake_hyde
        mock_complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_hyde_gracefully_falls_back_when_llm_unavailable() -> None:
    generator = VisualHyDEGenerator()

    with patch.object(LLMClient, "is_available", False):
        parsed = parse_query("heavy snow with trucks")
        caption = await generator.generate_hypothetical_caption("heavy snow with trucks", parsed)
        assert caption is None


def test_evaluator_satisfied_with_adequate_results() -> None:
    evaluator = RetrievalEvaluator()
    parsed = parse_query("snowy day")

    report = evaluator.evaluate(
        raw_matches_count=10,
        total_videos=5,
        below_threshold=False,
        parsed=parsed,
        retry_count=0,
    )
    assert report.verdict == EvaluationVerdict.SATISFIED


def test_evaluator_triggers_relaxation_when_over_constrained_and_empty() -> None:
    evaluator = RetrievalEvaluator()
    parsed = parse_query("rainy day without cars without people")

    report = evaluator.evaluate(
        raw_matches_count=0,
        total_videos=0,
        below_threshold=False,
        parsed=parsed,
        retry_count=0,
        max_loops=1,
    )
    assert report.verdict == EvaluationVerdict.NEEDS_RELAXATION
    assert report.relaxed_parsed is not None
    assert len(report.relaxed_parsed.excluded) < len(parsed.excluded)


@pytest.mark.asyncio
async def test_orchestrator_guardrail_rejects_instantly() -> None:
    orchestrator = TriTierAgentOrchestrator()
    parsed = parse_query("spiderman")

    mock_executor = AsyncMock()

    outcome, trace = await orchestrator.execute(
        "spiderman",
        parsed,
        retrieval_executor=mock_executor,
    )

    mock_executor.assert_not_awaited()
    assert trace.route == SearchRoute.REJECT_OOD
    assert outcome.total_videos == 0
    assert outcome.below_threshold is True
    assert "domain_guardrail" in outcome.signals_used
