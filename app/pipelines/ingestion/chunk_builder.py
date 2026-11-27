"""Retrieval windows within a semantic scene, sharing sampled frame references."""

from __future__ import annotations

import math
import time
import uuid
from bisect import bisect_left
from collections.abc import Iterator

from pipelines.common.types import SceneRecord, SemanticScene
from pipelines.ingestion.scene_builder import SCENE_NAMESPACE


def iter_chunks(
    scene: SemanticScene,
    *,
    duration_s: float,
    stride_s: float,
    ingestion_identity: str,
    diagnostics: dict | None = None,
) -> Iterator[SceneRecord]:
    if not all(math.isfinite(value) and value > 0 for value in (duration_s, stride_s)):
        raise ValueError("Retrieval window durations must be finite and positive")
    duration_ms, stride_ms = round(duration_s * 1000), round(stride_s * 1000)
    if not 0 < stride_ms <= duration_ms:
        raise ValueError("Retrieval chunk stride must not exceed its duration")
    if scene.end_ms <= scene.start_ms or not scene.frames:
        raise ValueError("Semantic scene has no valid temporal coverage")
    timestamps = [frame.timestamp_ms for frame in scene.frames]
    if (
        timestamps[0] < scene.start_ms
        or timestamps[-1] >= scene.end_ms
        or any(right <= left for left, right in zip(timestamps, timestamps[1:]))
    ):
        raise ValueError("Chunk frame references must be ordered within the semantic scene")
    start = scene.start_ms
    while start < scene.end_ms:
        started = time.perf_counter()
        end = min(start + duration_ms, scene.end_ms)
        frames = list(scene.frames[bisect_left(timestamps, start) : bisect_left(timestamps, end)])
        if not frames:
            raise ValueError("Retrieval chunk has no sampled frame evidence")
        if any(frame.embedding is None for frame in frames):
            raise ValueError("Retrieval chunks require existing SigLIP embeddings")
        dimension = len(frames[0].embedding)
        if any(len(frame.embedding) != dimension for frame in frames):
            raise ValueError("Retrieval chunk has inconsistent SigLIP dimensions")
        chunk = SceneRecord(
            scene_id=str(
                uuid.uuid5(SCENE_NAMESPACE, f"{scene.scene_id}:{ingestion_identity}:{start}:{end}")
            ),
            video_id=scene.video_id,
            start_ms=start,
            end_ms=end,
            keyframes=frames,
            siglip_sum=[
                math.fsum(frame.embedding[i] for frame in frames) for i in range(dimension)
            ],
            metadata={
                "semantic_scene_id": scene.scene_id,
                "semantic_start_ms": scene.start_ms,
                "semantic_end_ms": scene.end_ms,
                "boundary_reason": scene.boundary_reason,
                "boundary_score": scene.boundary_score,
                "sampled_frame_count": len(frames),
            },
            behaviors=sorted(
                {
                    behavior
                    for frame in frames
                    for behavior in frame.behaviors
                    if behavior.start_ms < end and behavior.end_ms > start
                },
                key=lambda behavior: (behavior.start_ms, behavior.kind),
            ),
            privacy_status="verified"
            if all(frame.privacy_status == "verified" for frame in frames)
            else "failed",
        )
        if diagnostics is not None:
            diagnostics["chunking_duration_ms"] = (
                diagnostics.get("chunking_duration_ms", 0) + (time.perf_counter() - started) * 1000
            )
            diagnostics["chunks_created"] = diagnostics.get("chunks_created", 0) + 1
        yield chunk
        if end == scene.end_ms:
            break
        start += stride_ms
