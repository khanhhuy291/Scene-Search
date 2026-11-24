"""Temporal scene grouping with confirmed content boundaries."""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Iterator

from core.config import VideoSettings
from ml.vectors import normalize_vectors
from pipelines.common.types import FrameRecord, SceneRecord

SCENE_NAMESPACE = uuid.UUID("babfb50b-01e3-49cd-8d69-b34a5d20c574")


def scene_id(video_id: str, pipeline_version: str, index: int) -> str:
    return str(uuid.uuid5(SCENE_NAMESPACE, f"{video_id}:{pipeline_version}:{index}"))


def _distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Scene has inconsistent SigLIP dimensions")
    return min(2.0, max(0.0, 1.0 - math.fsum(a * b for a, b in zip(left, right, strict=True))))


def _sum_vectors(frames: list[FrameRecord]) -> list[float] | None:
    vectors = [f.embedding for f in frames]
    if any(v is None for v in vectors):
        return None
    size = len(vectors[0])
    if any(len(v) != size for v in vectors):
        raise ValueError("Scene has inconsistent SigLIP dimensions")
    return [math.fsum(v[i] for v in vectors) for i in range(size)]


def _has_gap(previous: FrameRecord, frame: FrameRecord, gap_ms: int) -> bool:
    old_sequence = previous.metadata.get("sample_sequence")
    sequence = frame.metadata.get("sample_sequence")
    if old_sequence is not None and sequence is not None and sequence != old_sequence + 1:
        return True
    # Normal sample cadence/PTS rounding is not lost data. Measure only the
    # uncovered interval, without extending the previous sample's coverage.
    covered_until = previous.timestamp_ms
    if previous.covers_end_ms is not None and previous.covers_end_ms > previous.timestamp_ms:
        covered_until = previous.covers_end_ms
    return frame.timestamp_ms - covered_until > gap_ms


def iter_scenes(
    frames: Iterable[FrameRecord],
    *,
    video_id: str,
    pipeline_version: str,
    max_duration_sec: float = 5.0,
    gap_threshold_sec: float = 2.0,
    sample_interval_ms: int = 0,
    video_end_ms: int | None = None,
    settings: VideoSettings | None = None,
) -> Iterator[SceneRecord]:
    if max_duration_sec <= 0 or gap_threshold_sec < 0:
        raise ValueError("scene durations must be positive")
    settings = settings or VideoSettings()
    max_ms, gap_ms = round(max_duration_sec * 1000), round(gap_threshold_sec * 1000)
    current: list[FrameRecord] = []
    pending: list[FrameRecord] = []
    current_sum: list[float] | None = None
    scene_index = 0
    previous: FrameRecord | None = None
    previous_direction: list[float] | None = None

    def append(frame: FrameRecord) -> None:
        nonlocal current_sum
        current.append(frame)
        vector = frame.embedding
        if current_sum is None:
            current_sum = list(vector)
        elif len(vector) != len(current_sum):
            raise ValueError("Scene has inconsistent SigLIP dimensions")
        else:
            current_sum = [a + b for a, b in zip(current_sum, vector, strict=True)]

    def merge_pending() -> None:
        for buffered in pending:
            append(buffered)
        pending.clear()

    def close(limit_ms: int | None = None) -> SceneRecord:
        nonlocal scene_index, current_sum
        start_ms = current[0].timestamp_ms
        last = current[-1]
        end_ms = min(
            last.covers_end_ms
            if last.covers_end_ms is not None and last.covers_end_ms > last.timestamp_ms
            else last.timestamp_ms + max(1, sample_interval_ms),
            start_ms + max_ms,
            video_end_ms if video_end_ms is not None else start_ms + max_ms,
            limit_ms if limit_ms is not None else start_ms + max_ms,
        )
        for frame in current:
            if frame.covers_end_ms is not None:
                frame.covers_end_ms = min(frame.covers_end_ms, end_ms)
        scene = SceneRecord(
            scene_id=scene_id(video_id, pipeline_version, scene_index),
            video_id=video_id,
            start_ms=start_ms,
            end_ms=end_ms,
            keyframes=list(current),
            metadata={"sampled_frame_count": len(current)},
            siglip_sum=list(current_sum) if current_sum is not None else _sum_vectors(current),
            behaviors=sorted(
                {b for f in current for b in f.behaviors}, key=lambda b: (b.start_ms, b.kind)
            ),
            privacy_status="verified"
            if all(f.privacy_status == "verified" for f in current)
            else "failed",
        )
        scene_index += 1
        current.clear()
        current_sum = None
        return scene

    source = iter(frames)
    try:
        for frame in source:
            if video_end_ms is not None and frame.timestamp_ms >= video_end_ms:
                continue
            if frame.embedding is None:
                raise ValueError("Content segmentation requires SigLIP embeddings")
            direction = normalize_vectors([frame.embedding], dimension=len(frame.embedding))[0]
            frame.embedding = direction
            if current:
                too_long = frame.timestamp_ms - current[0].timestamp_ms >= max_ms
                gap = previous is not None and _has_gap(previous, frame, gap_ms)
                if too_long or gap:
                    merge_pending()
                    yield close()
            if not current:
                append(frame)
            elif pending:
                summed = _sum_vectors(pending)
                centroid = normalize_vectors([summed], dimension=len(summed))[0]
                if _distance(direction, centroid) <= settings.scene_global_distance:
                    pending.append(frame)
                    elapsed = frame.timestamp_ms - pending[0].timestamp_ms
                    if len(pending) >= 2 and elapsed >= settings.scene_confirmation_s * 1000:
                        onset = pending[0].timestamp_ms
                        completed = close(onset)
                        merge_pending()
                        yield completed
                else:
                    # Reject the transient; its return edge must not seed another
                    # local candidate on this same sample (e.g. a one-frame flash).
                    merge_pending()
                    append(frame)
            else:
                centroid = normalize_vectors([current_sum], dimension=len(current_sum))[0]
                local = _distance(direction, previous_direction)
                global_distance = _distance(direction, centroid)
                local_change = local > settings.scene_local_distance
                global_change = global_distance > settings.scene_global_distance
                enough_duration = (
                    frame.timestamp_ms - current[0].timestamp_ms
                    >= settings.scene_min_duration_s * 1000
                )
                if local_change or (global_change and enough_duration):
                    pending.append(frame)
                else:
                    append(frame)
            previous, previous_direction = frame, direction
        merge_pending()
        if current:
            yield close()
    finally:
        if hasattr(source, "close"):
            source.close()


def build_scenes(
    frames: Iterable[FrameRecord],
    *,
    video_id: str,
    pipeline_version: str,
    max_duration_sec: float = 5.0,
    gap_threshold_sec: float = 2.0,
    sample_interval_ms: int = 0,
    video_end_ms: int | None = None,
    settings: VideoSettings | None = None,
) -> list[SceneRecord]:
    """Compatibility materializer for callers that need a scene list."""
    return list(
        iter_scenes(
            frames,
            video_id=video_id,
            pipeline_version=pipeline_version,
            max_duration_sec=max_duration_sec,
            gap_threshold_sec=gap_threshold_sec,
            sample_interval_ms=sample_interval_ms,
            video_end_ms=video_end_ms,
            settings=settings,
        )
    )


__all__ = ["SCENE_NAMESPACE", "build_scenes", "iter_scenes", "scene_id"]
