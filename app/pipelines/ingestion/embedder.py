"""Batched scene embedding supporting SigLIP and Qwen models."""

from __future__ import annotations

import math
import sys
import time
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
    scenes_or_frames: Iterable[FrameRecord],
    *,
    encoder: Encoder,
    batch_size: int,
    reuse_existing: bool = False,
) -> list[FrameRecord]:
    """Attach Qwen multimodal/visual vectors to retained frames."""
    frames = list(scenes_or_frames)
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    pending = [frame for frame in frames if not reuse_existing or frame.qwen_embedding is None]
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
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
    qwen_encoder: Encoder,
    siglip_encoder: Encoder,
    caption_encoder: Encoder,
    version: str | None = None,
    batch_size: int = 8,
    metrics: dict | None = None,
) -> list[EmbeddingRecord]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    version = version or qwen_encoder.model_version
    output: list[EmbeddingRecord] = []
    for scene in scenes:
        pool_started = time.perf_counter()
        qwen_vectors = [frame.qwen_embedding for frame in scene.keyframes]
        if any(vector is None for vector in qwen_vectors):
            images = [frame.image for frame in scene.keyframes]
            qwen_vectors = []
            for start in range(0, len(images), batch_size):
                qwen_vectors.extend(qwen_encoder.encode_images(images[start : start + batch_size]))
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
        if metrics is not None:
            metrics["pooling_duration_ms"] = (
                metrics.get("pooling_duration_ms", 0) + (time.perf_counter() - pool_started) * 1000
            )
        named_vectors = {"qwen": qwen_vec, "siglip": siglip_vec}
        data = scene.metadata.get("vlm_data") or {}
        caption = (data.get("metadata") or {}).get("caption", "").strip()
        status = (data.get("enrichment") or {}).get("status")
        if caption and status in ("success", "partial"):
            caption_started = time.perf_counter()
            try:
                named_vectors["caption"] = normalize_vectors(
                    caption_encoder.encode_texts([caption]),
                    dimension=caption_encoder.dimension,
                    count=1,
                )[0]
            except ValueError as exc:
                raise EmbeddingError(str(exc), stage="embedding") from exc
            finally:
                if metrics is not None:
                    metrics["caption_embedding_duration_ms"] = (
                        metrics.get("caption_embedding_duration_ms", 0)
                        + (time.perf_counter() - caption_started) * 1000
                    )
            scene.metadata["caption_embedding_status"] = "ready"
        else:
            scene.metadata["caption_embedding_status"] = "not_available"
        output.append(
            EmbeddingRecord(
                scene.scene_id,
                named_vectors,
                model="qwen+siglip",
                version=version,
            )
        )

    return output


__all__ = ["embed_frames", "embed_frames_qwen", "embed_scenes"]
