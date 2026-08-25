"""Configurable streaming frame sampler."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from pipelines.common.types import FrameRecord


class UniformFrameSampler:
    """Baseline sampler; the interface permits a later adaptive implementation."""

    def __init__(self, fps: float = 1.0, *, max_gap_sec: float = 2.0) -> None:
        if fps <= 0 or max_gap_sec <= 0:
            raise ValueError("fps and max_gap_sec must be positive")
        self.interval_ms = max(1, round(1000 / fps))
        self.max_gap_ms = round(max_gap_sec * 1000)

    def sample(self, frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]:
        next_timestamp = 0
        last_emitted: int | None = None
        for frame in frames:
            forced = (
                last_emitted is not None and frame.timestamp_ms - last_emitted >= self.max_gap_ms
            )
            if frame.timestamp_ms < next_timestamp and not forced:
                frame.image.close()
                continue
            yield frame
            last_emitted = frame.timestamp_ms
            next_timestamp = frame.timestamp_ms + self.interval_ms


def sample_frames(
    frames: Iterable[FrameRecord], *, fps: float = 1.0, max_gap_sec: float = 2.0
) -> Iterator[FrameRecord]:
    return UniformFrameSampler(fps, max_gap_sec=max_gap_sec).sample(frames)


__all__ = ["UniformFrameSampler", "sample_frames"]
