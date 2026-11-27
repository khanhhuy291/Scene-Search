"""Timestamp-based bidirectional SigLIP change detection within a continuous span."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from statistics import median

from core.config import VideoSettings
from ml.vectors import normalize_vectors
from pipelines.common.types import FrameRecord, SceneBoundary


def pooled_direction(frames: list[FrameRecord]) -> list[float]:
    if not frames or any(frame.embedding is None for frame in frames):
        raise ValueError("Semantic pooling requires embedded frames")
    dimension = len(frames[0].embedding)
    vectors = normalize_vectors([frame.embedding for frame in frames], dimension=dimension)
    return normalize_vectors(
        [[math.fsum(vector[i] for vector in vectors) for i in range(dimension)]],
        dimension=dimension,
    )[0]


def cosine_distance(left: list[float], right: list[float]) -> float:
    return min(2.0, max(0.0, 1 - math.fsum(a * b for a, b in zip(left, right, strict=True))))


def change_scores(
    frames: list[FrameRecord],
    *,
    context_window_s: float,
    min_window_coverage: float = 0.0,
    diagnostics: list[dict] | None = None,
) -> list[float | None]:
    """Use rolling sums so each embedding enters and leaves each window once."""
    if not frames:
        return []
    if any(frame.embedding is None for frame in frames):
        raise ValueError("Semantic change detection requires SigLIP embeddings")
    if (
        not 0 <= min_window_coverage <= 1
        or not math.isfinite(context_window_s)
        or context_window_s <= 0
    ):
        raise ValueError("Invalid temporal window coverage policy")
    dimension = len(frames[0].embedding) if frames[0].embedding is not None else 0
    vectors = normalize_vectors([frame.embedding for frame in frames], dimension=dimension)
    timestamps = [frame.timestamp_ms for frame in frames]
    if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError("Semantic samples must have strictly increasing timestamps")
    window_ms = max(1, round(context_window_s * 1000))
    left_sum, right_sum = [0.0] * dimension, [0.0] * dimension
    left_start = right_end = 0
    scores = []
    cadence = (
        median([right - left for left, right in zip(timestamps, timestamps[1:])])
        if len(timestamps) > 1
        else 1
    )

    def add(total: list[float], vector: list[float], sign: int) -> None:
        for coordinate, value in enumerate(vector):
            total[coordinate] += sign * value

    for index, timestamp in enumerate(timestamps):
        if index:
            add(left_sum, vectors[index - 1], 1)
            add(right_sum, vectors[index - 1], -1)
        while left_start < index and timestamps[left_start] < timestamp - window_ms:
            add(left_sum, vectors[left_start], -1)
            left_start += 1
        while right_end < len(frames) and timestamps[right_end] < timestamp + window_ms:
            add(right_sum, vectors[right_end], 1)
            right_end += 1
        left_coverage = (
            max(0, timestamp - max(timestamp - window_ms, timestamps[left_start])) / window_ms
            if left_start < index
            else 0.0
        )
        last = frames[right_end - 1]
        support_end = (
            last.covers_end_ms
            if last.covers_end_ms is not None and last.covers_end_ms > last.timestamp_ms
            else last.timestamp_ms + cadence
        )
        right_coverage = max(0, min(timestamp + window_ms, support_end) - timestamp) / window_ms
        score, reason = None, "insufficient_coverage"
        if (
            left_coverage > 0
            and right_coverage > 0
            and min(left_coverage, right_coverage) >= min_window_coverage
        ):
            try:
                left, right = normalize_vectors([left_sum, right_sum], dimension=dimension)
                score = cosine_distance(left, right)
                reason = (
                    "full_context"
                    if min(left_coverage, right_coverage) >= 1
                    else "partial_context_fallback"
                )
            except ValueError:
                reason = "invalid_window_norm"
        scores.append(score)
        if diagnostics is not None:
            diagnostics.append(
                {
                    "timestamp_ms": timestamp,
                    "raw_score": score,
                    "left_coverage": left_coverage,
                    "right_coverage": right_coverage,
                    "reason": reason,
                }
            )
    return scores


def detect_boundaries(
    frames: list[FrameRecord], settings: VideoSettings, *, diagnostics: dict | None = None
) -> list[SceneBoundary]:
    """Return local peaks; callers split gaps before invoking this function."""
    if len(frames) < 2:
        return []
    details = []
    raw_scores = change_scores(
        frames,
        context_window_s=settings.semantic_context_window_s,
        min_window_coverage=settings.semantic_min_window_coverage,
        diagnostics=details,
    )
    valid = [index for index, score in enumerate(raw_scores) if score is not None]
    if diagnostics is not None:
        diagnostics.update(samples=details, unavailable_scores=len(frames) - len(valid))
    if not valid:
        return []
    times = [frames[index].timestamp_ms for index in valid]
    raw = [score for score in raw_scores if score is not None]
    prefix = [0.0]
    for score in raw:
        prefix.append(prefix[-1] + score)
    half_window = settings.semantic_smoothing_window_s * 500
    scores = []
    for timestamp in times:
        start = bisect_left(times, timestamp - half_window)
        end = bisect_right(times, timestamp + half_window)
        scores.append((prefix[end] - prefix[start]) / (end - start))
    threshold = settings.semantic_threshold_floor
    if settings.semantic_adaptive_threshold and len(scores) >= 3:
        center = median(scores)
        mad = median(abs(score - center) for score in scores)
        threshold = max(threshold, center + settings.semantic_mad_multiplier * mad)
    peaks = []
    index = 0
    while index < len(scores):
        end = index + 1
        while end < len(scores) and math.isclose(scores[end], scores[index], abs_tol=1e-12):
            end += 1
        score = scores[index]
        if (
            score >= threshold
            and (index == 0 or score > scores[index - 1])
            and (end == len(scores) or score > scores[end])
        ):
            midpoint = (times[index] + times[end - 1]) / 2
            peak = min(range(index, end), key=lambda i: (abs(times[i] - midpoint), times[i]))
            # Smoothing decides whether a change is credible; the raw maximum
            # in that neighborhood localizes its onset without a smoothing shift.
            start = bisect_left(times, times[peak] - half_window)
            stop = bisect_right(times, times[peak] + half_window)
            onset = max(
                range(start, stop),
                key=lambda i: (raw[i], -abs(times[i] - times[peak]), -times[i]),
            )
            peaks.append(
                SceneBoundary(valid[onset], score, raw_score=raw[onset], threshold=threshold)
            )
        index = end
    if diagnostics is not None:
        diagnostics.update(
            threshold=threshold,
            boundary_candidates=len(peaks),
            smoothed_scores=[
                {"timestamp_ms": time, "score": score}
                for time, score in zip(times, scores, strict=True)
            ],
        )
    by_offset = {}
    for peak in peaks:
        previous = by_offset.get(peak.frame_offset)
        if previous is None or peak.score > previous.score:
            by_offset[peak.frame_offset] = peak
    return sorted(by_offset.values(), key=lambda boundary: boundary.frame_offset)
