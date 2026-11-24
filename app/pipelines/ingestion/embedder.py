"""Batched scene embedding supporting SigLIP and Qwen models."""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable, Iterator, Sequence
from itertools import islice

from ml.encoder import Encoder
from ml.vectors import normalize_vectors
from pipelines.common.errors import EmbeddingError
from pipelines.common.types import EmbeddingRecord, FrameRecord, SceneRecord


def embed_frames(
    scenes_or_frames: Iterable[FrameRecord], *, encoder: Encoder, batch_size: int
) -> list[FrameRecord]:
    """Attach visual vectors (e.g. SigLIP) to frames in bounded encoder batches for dedup."""
    return list(iter_embedded_frames(scenes_or_frames, encoder=encoder, batch_size=batch_size))


def iter_embedded_frames(
    frames: Iterable[FrameRecord], *, encoder: Encoder, batch_size: int
) -> Iterator[FrameRecord]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    source = iter(frames)
    try:
        while batch := list(islice(source, batch_size)):
            yield from _embed_batch(batch, encoder)
    finally:
        if hasattr(source, "close"):
            source.close()


def _embed_batch(batch: list[FrameRecord], encoder: Encoder) -> list[FrameRecord]:
    try:
        vectors = normalize_vectors(
            encoder.encode_images([f.image for f in batch]),
            dimension=encoder.dimension,
            count=len(batch),
        )
    except ValueError as exc:
        raise EmbeddingError(str(exc), stage="embedding") from exc
    for frame, vector in zip(batch, vectors, strict=True):
        frame.embedding = vector
    return batch


def embed_frames_qwen(
    scenes_or_frames: Iterable[FrameRecord], *, encoder: Encoder, batch_size: int
) -> list[FrameRecord]:
    """Attach Qwen multimodal/visual vectors to retained frames."""
    frames = list(scenes_or_frames)
    for start in range(0, len(frames), batch_size):
        batch = frames[start : start + batch_size]
        try:
            vectors = normalize_vectors(
                encoder.encode_images([frame.image for frame in batch]),
                dimension=encoder.dimension,
                count=len(batch),
            )
        except ValueError as exc:
            raise EmbeddingError(str(exc), stage="embedding") from exc
        for frame, vector in zip(batch, vectors, strict=True):
            frame.qwen_embedding = vector
    return frames


def _mean_normalized(vectors: Sequence[list[float]]) -> list[float]:
    if not vectors:
        raise EmbeddingError("Scene has no keyframe vectors", stage="embedding")
    size = len(vectors[0])
    if any(len(vector) != size for vector in vectors):
        raise EmbeddingError("Encoder returned inconsistent dimensions", stage="embedding")
    mean = [sum(vector[i] for vector in vectors) / len(vectors) for i in range(size)]
    norm = math.hypot(*mean)
    if not math.isfinite(norm) or norm <= sys.float_info.epsilon:
        raise EmbeddingError("Scene vector has zero or invalid norm", stage="embedding")
    return [value / norm for value in mean]


def embed_scenes(
    scenes: Sequence[SceneRecord],
    *,
    encoder: Encoder | None = None,
    qwen_encoder: Encoder | None = None,
    siglip_encoder: Encoder | None = None,
    expected_dimension: int = 2048,
    model: str = "qwen",
    version: str = "v1",
    batch_size: int = 8,
) -> list[EmbeddingRecord]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    primary_encoder = qwen_encoder or encoder
    if primary_encoder is None:
        raise ValueError("At least one encoder must be provided")

    output: list[EmbeddingRecord] = []
    for scene in scenes:
        if qwen_encoder is not None and siglip_encoder is not None:
            # Multi-vector (Qwen 2048-d + SigLIP 768-d)
            qwen_vectors = [frame.qwen_embedding for frame in scene.keyframes]
            if any(vector is None for vector in qwen_vectors):
                images = [frame.image for frame in scene.keyframes]
                qwen_vectors = []
                for start in range(0, len(images), batch_size):
                    qwen_vectors.extend(
                        qwen_encoder.encode_images(images[start : start + batch_size])
                    )
            qwen_vec = _mean_normalized(qwen_vectors)

            siglip_vectors = (
                [scene.siglip_sum]
                if scene.siglip_sum is not None
                else [frame.embedding for frame in scene.keyframes]
            )
            if any(vector is None for vector in siglip_vectors):
                images = [frame.image for frame in scene.keyframes]
                siglip_vectors = []
                for start in range(0, len(images), batch_size):
                    siglip_vectors.extend(
                        siglip_encoder.encode_images(images[start : start + batch_size])
                    )
            siglip_vec = _mean_normalized(siglip_vectors)

            output.append(
                EmbeddingRecord(
                    scene.scene_id,
                    {"qwen": qwen_vec, "siglip": siglip_vec},
                    model="qwen+siglip",
                    version=version,
                )
            )
        else:
            # Single-vector fallback
            vectors = [frame.embedding for frame in scene.keyframes]
            if any(vector is None for vector in vectors):
                images = [frame.image for frame in scene.keyframes]
                vectors = []
                for start in range(0, len(images), batch_size):
                    vectors.extend(
                        primary_encoder.encode_images(images[start : start + batch_size])
                    )
            vector = _mean_normalized(vectors)
            if len(vector) != expected_dimension:
                raise EmbeddingError(
                    f"Embedding dimension {len(vector)} does not match Qdrant dimension {expected_dimension}",
                    stage="embedding",
                )
            output.append(EmbeddingRecord(scene.scene_id, vector, model, version))

    return output


__all__ = ["embed_frames", "embed_frames_qwen", "embed_scenes"]
