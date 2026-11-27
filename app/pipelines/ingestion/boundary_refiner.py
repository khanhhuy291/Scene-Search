"""Refine semantic peaks without merging across the caller's continuity spans."""

from __future__ import annotations

from bisect import bisect_left

from core.config import VideoSettings
from ml.vectors import normalize_vectors
from pipelines.common.types import FrameRecord, SceneBoundary
from pipelines.ingestion.semantic_segmenter import cosine_distance, pooled_direction


def _distinct_short_interval(
    frames: list[FrameRecord], left: int, right: int, settings: VideoSettings
) -> bool:
    timestamps = [frame.timestamp_ms for frame in frames]
    context_ms = settings.semantic_context_window_s * 1000
    before = bisect_left(timestamps, timestamps[left] - context_ms)
    after = bisect_left(timestamps, timestamps[right] + context_ms)
    if before == left or after == right:
        return False
    middle = pooled_direction(frames[left:right])
    return all(
        cosine_distance(middle, pooled_direction(neighbor)) > settings.semantic_merge_distance
        for neighbor in (frames[before:left], frames[right:after])
    )


def refine_boundaries(
    frames: list[FrameRecord], candidates: list[SceneBoundary], settings: VideoSettings
) -> list[SceneBoundary]:
    if len({candidate.frame_offset for candidate in candidates}) != len(candidates):
        raise ValueError("Duplicate semantic boundary offset")
    selected: list[SceneBoundary] = []
    for candidate in sorted(
        candidates, key=lambda boundary: (-boundary.score, boundary.frame_offset)
    ):
        offset = candidate.frame_offset
        if not 0 < offset < len(frames):
            raise ValueError("Semantic boundary is outside its frame span")
        conflicts = [
            other
            for other in selected
            if abs(frames[offset].timestamp_ms - frames[other.frame_offset].timestamp_ms)
            < settings.semantic_min_scene_duration_s * 1000
        ]
        if all(
            _distinct_short_interval(
                frames, min(offset, other.frame_offset), max(offset, other.frame_offset), settings
            )
            for other in conflicts
        ):
            selected.append(candidate)
    selected.sort(key=lambda boundary: boundary.frame_offset)
    if not selected or not settings.semantic_merge_similar_scenes:
        return selected

    # Pool each initial segment once, then combine sums while merging. Strong
    # boundaries survive even when the two whole-scene means happen to be close.
    offsets = [0, *(boundary.frame_offset for boundary in selected), len(frames)]
    stack: list[tuple[SceneBoundary | None, list[float]]] = []
    for index, (start, end) in enumerate(zip(offsets, offsets[1:])):
        boundary = selected[index - 1] if index else None
        vectors = [frame.embedding for frame in frames[start:end]]
        total = [sum(vector[i] for vector in vectors) for i in range(len(vectors[0]))]
        while (
            stack
            and boundary is not None
            and boundary.score < settings.semantic_strong_boundary_distance
        ):
            previous_boundary, previous_sum = stack[-1]
            previous, current = normalize_vectors([previous_sum, total], dimension=len(total))
            if cosine_distance(previous, current) > settings.semantic_merge_distance:
                break
            stack.pop()
            total = [left + right for left, right in zip(previous_sum, total, strict=True)]
            boundary = previous_boundary
        stack.append((boundary, total))
    return [boundary for boundary, _ in stack if boundary is not None]
