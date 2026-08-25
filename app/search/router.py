"""Single-Pass LLM-based Domain Guardrail, Intent Classifier, and Visual-HyDE Generator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

from core.config import get_settings
from search.llm_client import get_llm_client
from search.query import ParsedQuery


class DomainVerdict(StrEnum):
    IN_DOMAIN = "in_domain"
    OUT_OF_DOMAIN = "out_of_domain"
    UNCERTAIN = "uncertain"


class SearchRoute(StrEnum):
    FAST_PATH = "fast_path"
    AGENTIC_PATH = "agentic_path"
    REJECT_OOD = "reject_ood"


@dataclass(frozen=True)
class UnifiedAnalysisResult:
    route: SearchRoute
    domain_verdict: DomainVerdict
    is_driving_scene: bool
    reason: str
    visual_hyde_caption: str | None = None


# Fast zero-latency rejection patterns for obvious nonsense/entertainment
_FAST_OOD_PATTERNS: tuple[str, ...] = (
    r"(?i)(spiderman|spider-man|batman|superman|ironman|iron man|avengers|hulk|thor)",
    r"(?i)(pokemon|pikachu|anime|naruto|goku|doraemon|manga)",
    r"(?i)(pizza|burger|pasta|noodle|soup|recipe|cooking|baking|nấu ăn|nấu phở|làm bánh)",
    r"(?i)(bitcoin|ethereum|crypto|stock market|forex)",
    r"(?i)(football|soccer|basketball|tennis|messi|ronaldo|ngoại hạng anh)",
    r"(?i)(elon musk|trump|biden|putin|celebrity|ca sĩ|diễn viên)",
    r"(?i)(code python|javascript|html|css|equation|giải phương trình|toán học)",
)

UNIFIED_ANALYSIS_SYSTEM_PROMPT = """You are the intelligence gateway for SceneSearch, a traffic and street camera search system.

Analyze user query and output ONLY a raw JSON object (no thinking, no reasoning, no markdown):
{
  "is_driving_scene": boolean, // true for any scene observable from a vehicle, dashcam, traffic or street camera (including cars, trucks, bikes, pedestrians, animals/pets on road or roadside, traffic lights, signs, parking, weather, road conditions). ONLY false for completely non-visual/unrelated topics like cooking recipes, video games, celebrities, math equations, or software code.
  "reason": "short explanation under 10 words",
  "is_complex": boolean, // true if describing maneuvers/accidents/interactions. false for simple objects.
  "visual_hyde_caption": "2-3 sentences of dashcam/street POV scene description in English (or null)"
}
"""


class UnifiedAgentRouter:
    """Unified single-pass Domain Guardrail, Intent Classifier, and HyDE Generator."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm = get_llm_client()

    def _fast_lexical_ood_check(self, query: str) -> bool:
        lower = query.lower().strip()
        return any(re.search(pat, lower) for pat in _FAST_OOD_PATTERNS)

    async def analyze(
        self,
        raw_query: str,
        parsed: ParsedQuery,
    ) -> UnifiedAnalysisResult:
        """Perform unified classification and optional HyDE expansion in one roundtrip."""
        settings = self._settings.search

        # 1. Tier 0: Fast lexical reject (0ms)
        if settings.domain_guardrail_enabled and self._fast_lexical_ood_check(raw_query):
            return UnifiedAnalysisResult(
                route=SearchRoute.REJECT_OOD,
                domain_verdict=DomainVerdict.OUT_OF_DOMAIN,
                is_driving_scene=False,
                reason="Query references subjects outside driving domain (Fast Filter)",
                visual_hyde_caption=None,
            )

        # 2. If agentic/LLM is disabled or not available, use fast path heuristics
        if not settings.agentic_enabled or not self._llm.is_available:
            return UnifiedAnalysisResult(
                route=SearchRoute.FAST_PATH,
                domain_verdict=DomainVerdict.IN_DOMAIN,
                is_driving_scene=True,
                reason="Fast-Path heuristic (LLM disabled or unavailable)",
                visual_hyde_caption=None,
            )

        # 3. Tier 1: Unified LLM Analysis (1 single roundtrip)
        prompt = (
            f"User query: {raw_query}\n"
            f"Required={list(parsed.required)}, Excluded={list(parsed.excluded)}"
        )

        try:
            response_text = await self._llm.complete(
                prompt=prompt,
                system_prompt=UNIFIED_ANALYSIS_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            if response_text:
                # Strip potential reasoning tags <think>...</think>
                cleaned = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
                # Find the JSON object inside the response
                match = re.search(r"\{[\s\S]*\}", cleaned)
                if not match:
                    logger.warning("No JSON found in LLM response: {!r}", response_text[:120])
                    data = {}
                else:
                    data = json.loads(match.group(0))

                is_driving = bool(data.get("is_driving_scene", True))
                reason = str(data.get("reason", "LLM domain evaluation"))
                is_complex = bool(data.get("is_complex", False))
                hyde_caption = data.get("visual_hyde_caption")

                if not is_driving:
                    logger.info("LLM Guardrail rejected OOD: {!r} ({})", raw_query, reason)
                    return UnifiedAnalysisResult(
                        route=SearchRoute.REJECT_OOD,
                        domain_verdict=DomainVerdict.OUT_OF_DOMAIN,
                        is_driving_scene=False,
                        reason=reason,
                        visual_hyde_caption=None,
                    )

                route = (
                    SearchRoute.AGENTIC_PATH
                    if (is_complex or hyde_caption)
                    else SearchRoute.FAST_PATH
                )
                return UnifiedAnalysisResult(
                    route=route,
                    domain_verdict=DomainVerdict.IN_DOMAIN,
                    is_driving_scene=True,
                    reason=reason,
                    visual_hyde_caption=hyde_caption if settings.hyde_enabled else None,
                )
        except Exception as exc:
            logger.warning("Unified LLM Analysis encountered error, falling back: {}", exc)

        # Fallback to in-domain fast path
        return UnifiedAnalysisResult(
            route=SearchRoute.FAST_PATH,
            domain_verdict=DomainVerdict.IN_DOMAIN,
            is_driving_scene=True,
            reason="Fallback to Fast-Path",
            visual_hyde_caption=None,
        )


_unified_router: UnifiedAgentRouter | None = None


def get_unified_router() -> UnifiedAgentRouter:
    """Return process-singleton UnifiedAgentRouter."""
    global _unified_router
    if _unified_router is None:
        _unified_router = UnifiedAgentRouter()
    return _unified_router
