"""Visual-HyDE (Hypothetical Document Embeddings for Video Scene Search)."""

from __future__ import annotations

from loguru import logger

from core.config import get_settings
from search.llm_client import get_llm_client
from search.query import ParsedQuery

HYDE_SYSTEM_PROMPT = """You are an autonomous vehicle vision expert and dashcam scene describer.
Your task is to convert a user query into a vivid, objective, visual caption describing
a forward-facing dashcam point of view (POV).

Rules:
1. Write 2 to 4 sentences strictly describing what is visually observable.
2. Include concrete visual details: road surface, lighting, weather, and surroundings.
3. If the user query is in Vietnamese, translate and expand it into English,
   because visual encoders are trained on English vision-language captions.
4. Do NOT include markdown, prefixes, quotes, explanations, or meta-commentary.
5. If the query asks for absence (e.g. "without pedestrians"), describe a clear roadway.
"""


class VisualHyDEGenerator:
    """Generates synthetic dashcam scene captions to bridge text-to-video representation gaps."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm = get_llm_client()

    async def generate_hypothetical_caption(
        self,
        raw_query: str,
        parsed: ParsedQuery,
    ) -> str | None:
        """Generate a rich visual dashcam description for embedding."""
        if not self._settings.search.hyde_enabled or not self._llm.is_available:
            return None

        prompt = (
            f"User driving scene query: {raw_query}\n"
            f"Required: {list(parsed.required)}, Excluded: {list(parsed.excluded)}\n\n"
            "Generate the visual dashcam POV scene caption:"
        )

        try:
            caption = await self._llm.complete(
                prompt=prompt,
                system_prompt=HYDE_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=200,
            )
            if caption:
                logger.debug("Generated Visual-HyDE caption: {}", caption)
                return caption
        except Exception as exc:
            logger.warning("Visual-HyDE generation failed, falling back: {}", exc)

        return None


_hyde_generator: VisualHyDEGenerator | None = None


def get_hyde_generator() -> VisualHyDEGenerator:
    """Return process-singleton VisualHyDEGenerator."""
    global _hyde_generator
    if _hyde_generator is None:
        _hyde_generator = VisualHyDEGenerator()
    return _hyde_generator
