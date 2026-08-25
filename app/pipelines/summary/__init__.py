"""Scene summary pipeline package."""

from pipelines.summary.summarizer import (
    SceneSummaryRecord,
    build_scene_text_summary,
    embed_scene_summaries,
)

__all__ = [
    "SceneSummaryRecord",
    "build_scene_text_summary",
    "embed_scene_summaries",
]
