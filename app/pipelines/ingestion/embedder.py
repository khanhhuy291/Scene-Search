"""Batched scene embedding using the existing process-scoped encoder."""

from __future__ import annotations

import math
from collections.abc import Sequence

from ml.encoder import Encoder
from pipelines.common.errors import EmbeddingError
from pipelines.common.types import EmbeddingRecord, SceneRecord


def embed_frames(scenes_or_frames, *, encoder: Encoder, batch_size: int):
    """Attach image vectors to frames in bounded encoder batches."""
    frames = list(scenes_or_frames)
    for start in range(0, len(frames), batch_size):
        batch = frames[start : start + batch_size]
        vectors = encoder.encode_images([frame.image for frame in batch])
        if len(vectors) != len(batch):
            raise EmbeddingError("Encoder returned the wrong number of vectors", stage="embedding")
        for frame, vector in zip(batch, vectors, strict=True):
            frame.embedding = vector
    return frames


def _mean_normalized(vectors: Sequence[list[float]]) -> list[float]:
    if not vectors:
        raise EmbeddingError("Scene has no keyframe vectors", stage="embedding")
    size = len(vectors[0])
    if any(len(vector) != size for vector in vectors):
        raise EmbeddingError("Encoder returned inconsistent dimensions", stage="embedding")
    mean = [sum(vector[i] for vector in vectors) / len(vectors) for i in range(size)]
    norm = math.sqrt(sum(value * value for value in mean))
    return [value / norm for value in mean] if norm else mean


def embed_scenes(
    scenes: Sequence[SceneRecord],
    *,
    encoder: Encoder,
    expected_dimension: int,
    model: str,
    version: str,
    batch_size: int,
) -> list[EmbeddingRecord]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    output: list[EmbeddingRecord] = []
    for scene in scenes:
        vectors = [frame.embedding for frame in scene.keyframes]
        if any(vector is None for vector in vectors):
            images = [frame.image for frame in scene.keyframes]
            vectors = []
            for start in range(0, len(images), batch_size):
                vectors.extend(encoder.encode_images(images[start : start + batch_size]))
        vector = _mean_normalized(vectors)
        if len(vector) != expected_dimension:
            raise EmbeddingError(
                f"Embedding dimension {len(vector)} does not match Qdrant dimension "
                f"{expected_dimension}",
                stage="embedding",
            )
        output.append(EmbeddingRecord(scene.scene_id, vector, model, version))
    return output


__all__ = ["embed_frames", "embed_scenes"]
