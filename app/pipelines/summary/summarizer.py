"""Summary generation and embedding pipeline stage.

Consumes scene keyframes, object summaries, and text descriptions to produce
multimodal summary embeddings for search and vector indexing using Qwen/Qwen3-VL-Embedding-2B.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ml.qwen_encoder import QwenVLEmbeddingClient, get_qwen_embedding_client
from pipelines.common.errors import EmbeddingError
from pipelines.common.types import SceneRecord

if TYPE_CHECKING:  # pragma: no cover
    from PIL.Image import Image


@dataclass
class SceneSummaryRecord:
    """Represents a generated scene summary with vector embedding."""

    scene_id: str
    video_id: str
    summary_text: str
    embedding: list[float]
    model_name: str = "Qwen/Qwen3-VL-Embedding-2B"
    model_version: str = "qwen3-vl-embedding-2b-v1"


def build_scene_text_summary(scene: SceneRecord, extra_context: str | None = None) -> str:
    """Construct a descriptive textual summary for a scene from its metadata and objects."""
    parts: list[str] = []

    if extra_context:
        parts.append(extra_context)

    start_s = getattr(scene, "start_ms", 0) / 1000.0
    end_s = getattr(scene, "end_ms", 0) / 1000.0
    parts.append(f"Scene duration {start_s:.1f}s to {end_s:.1f}s.")

    keyframes = getattr(scene, "keyframes", [])
    if keyframes:
        parts.append(f"Contains {len(keyframes)} keyframes.")

    # Extract detected object labels from keyframe detections or metadata
    objects: list[str] = []
    for kf in keyframes:
        for det in getattr(kf, "detections", []):
            if hasattr(det, "class_name"):
                objects.append(det.class_name)
    if objects:
        unique_obj = sorted(set(objects))
        parts.append(f"Detected objects: {', '.join(unique_obj)}.")

    behaviors = getattr(scene, "behaviors", [])
    if behaviors:
        unique_beh = sorted({str(getattr(b, "kind", b)) for b in behaviors if b})
        parts.append(f"Observed behaviors: {', '.join(unique_beh)}.")

    return " ".join(parts)


def embed_scene_summaries(
    scenes: Sequence[SceneRecord],
    *,
    client: QwenVLEmbeddingClient | None = None,
    batch_size: int = 16,
    include_keyframes: bool = True,
    extra_descriptions: dict[str, str] | None = None,
) -> list[SceneSummaryRecord]:
    """Generate multimodal scene summary embeddings for a list of scene records.

    If keyframes are available and `include_keyframes` is True, generates joint
    multimodal (image + text summary) embeddings. Otherwise generates text-based summary embeddings.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    qwen_client = client or get_qwen_embedding_client()
    results: list[SceneSummaryRecord] = []
    descriptions = extra_descriptions or {}

    for scene in scenes:
        scene_id = getattr(scene, "scene_id", "scene_unknown")
        video_id = getattr(scene, "video_id", "video_unknown")
        text_desc = descriptions.get(scene_id) or build_scene_text_summary(scene)

        keyframes = getattr(scene, "keyframes", [])
        image_sample: Image | None = None
        if include_keyframes and keyframes:
            # Pick representative keyframe (middle keyframe)
            mid_idx = len(keyframes) // 2
            image_sample = getattr(keyframes[mid_idx], "image", None)

        try:
            if image_sample is not None:
                vectors = qwen_client.encode_multimodal([image_sample], [text_desc])
            else:
                vectors = qwen_client.encode_texts([text_desc])

            if not vectors:
                raise EmbeddingError("Qwen client returned no vector", stage="summary")

            results.append(
                SceneSummaryRecord(
                    scene_id=scene_id,
                    video_id=video_id,
                    summary_text=text_desc,
                    embedding=vectors[0],
                    model_name=qwen_client.settings.qwen_model_name,
                    model_version=qwen_client.model_version,
                )
            )
        except Exception as exc:
            raise EmbeddingError(
                f"Failed to generate summary embedding for scene {scene_id}: {exc}",
                stage="summary",
            ) from exc

    return results


__all__ = [
    "SceneSummaryRecord",
    "build_scene_text_summary",
    "embed_scene_summaries",
]
