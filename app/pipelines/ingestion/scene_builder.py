"""Temporal scene grouping; sampled frames are not treated as scenes."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from pipelines.common.types import FrameRecord, SceneRecord

SCENE_NAMESPACE = uuid.UUID("babfb50b-01e3-49cd-8d69-b34a5d20c574")


def scene_id(video_id: str, pipeline_version: str, index: int) -> str:
    return str(uuid.uuid5(SCENE_NAMESPACE, f"{video_id}:{pipeline_version}:{index}"))


def build_scenes(
    frames: Iterable[FrameRecord],
    *,
    video_id: str,
    pipeline_version: str,
    max_duration_sec: float = 5.0,
    gap_threshold_sec: float = 2.0,
) -> list[SceneRecord]:
    if max_duration_sec <= 0 or gap_threshold_sec < 0:
        raise ValueError("scene durations must be positive")
    max_duration_ms = round(max_duration_sec * 1000)
    gap_ms = round(gap_threshold_sec * 1000)
    scenes: list[SceneRecord] = []
    current: list[FrameRecord] = []

    def close() -> None:
        if not current:
            return
        index = len(scenes)
        behaviors = {behavior for frame in current for behavior in frame.behaviors}
        scenes.append(
            SceneRecord(
                scene_id=scene_id(video_id, pipeline_version, index),
                video_id=video_id,
                start_ms=current[0].covers_start_ms or current[0].timestamp_ms,
                end_ms=current[-1].covers_end_ms or current[-1].timestamp_ms,
                keyframes=list(current),
                metadata={"sampled_frame_count": len(current)},
                behaviors=sorted(behaviors, key=lambda item: (item.start_ms, item.kind)),
                privacy_status=(
                    "verified"
                    if all(frame.privacy_status == "verified" for frame in current)
                    else "failed"
                ),
            )
        )
        current.clear()

    previous_ms: int | None = None
    for frame in frames:
        if current:
            too_long = frame.timestamp_ms - current[0].timestamp_ms > max_duration_ms
            gap = previous_ms is not None and frame.timestamp_ms - previous_ms > gap_ms
            if too_long or gap:
                close()
        current.append(frame)
        previous_ms = frame.timestamp_ms
    close()
    return scenes


__all__ = ["SCENE_NAMESPACE", "build_scenes", "scene_id"]
