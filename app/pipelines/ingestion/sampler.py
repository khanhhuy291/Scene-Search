"""Configurable streaming frame sampler."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from pipelines.common.types import FrameRecord
from pipelines.ingestion.timeline import DecodeTimeline


class UniformFrameSampler:
    """Baseline sampler; the interface permits a later adaptive implementation."""

    def __init__(self, fps: float = 1.0, *, max_gap_sec: float = 2.0) -> None:
        if fps <= 0 or max_gap_sec <= 0:
            raise ValueError("fps and max_gap_sec must be positive")
        self.interval_ms = max(1, round(1000 / fps))
        self.max_gap_ms = round(max_gap_sec * 1000)

    def sample(
        self,
        frames: Iterable[FrameRecord],
        *,
        video_end_ms: int | None = None,
        timeline: DecodeTimeline | None = None,
    ) -> Iterator[FrameRecord]:
        pending: FrameRecord | None = None
        source = iter(frames)
        try:
            next_timestamp = 0
            last_emitted: int | None = None
            sequence = 0
            for frame in source:
                forced = (
                    last_emitted is not None
                    and frame.timestamp_ms - last_emitted >= self.max_gap_ms
                )
                if frame.timestamp_ms < next_timestamp and not forced:
                    frame.image.close()
                    continue
                frame.metadata["sample_sequence"] = sequence
                sequence += 1
                frame.covers_start_ms = frame.timestamp_ms
                if pending is not None:
                    pending.covers_end_ms = min(
                        pending.timestamp_ms + self.interval_ms, frame.timestamp_ms
                    )
                    if video_end_ms is not None:
                        pending.covers_end_ms = min(pending.covers_end_ms, video_end_ms)
                    emitted = pending
                    pending = frame
                    yield emitted
                pending = frame
                last_emitted = frame.timestamp_ms
                next_timestamp = frame.timestamp_ms + self.interval_ms
            if pending is not None:
                end_ms = video_end_ms
                if end_ms is None and timeline is not None:
                    end_ms = timeline.end_ms
                pending.covers_end_ms = min(
                    pending.timestamp_ms + self.interval_ms,
                    end_ms if end_ms is not None else pending.timestamp_ms + self.interval_ms,
                )
                if pending.covers_end_ms > pending.timestamp_ms:
                    pending.metadata["duration_source"] = (
                        "probe"
                        if video_end_ms is not None
                        else timeline.duration_source
                        if timeline is not None
                        else "estimated_sample_interval"
                    )
                    emitted = pending
                    pending = None
                    yield emitted
                else:
                    pending.close()
                    pending = None
        finally:
            if pending is not None:
                pending.close()
            if hasattr(source, "close"):
                source.close()


def sample_frames(
    frames: Iterable[FrameRecord],
    *,
    fps: float = 1.0,
    max_gap_sec: float = 2.0,
    video_end_ms: int | None = None,
    timeline: DecodeTimeline | None = None,
) -> Iterator[FrameRecord]:
    return UniformFrameSampler(fps, max_gap_sec=max_gap_sec).sample(
        frames, video_end_ms=video_end_ms, timeline=timeline
    )


__all__ = ["UniformFrameSampler", "sample_frames"]
