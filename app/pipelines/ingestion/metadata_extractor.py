"""Metadata stage that never invents unavailable observations or inference."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from pipelines.common.types import FrameRecord


def extract_metadata(frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]:
    for frame in frames:
        frame.metadata.setdefault("timestamp", {"value_ms": frame.timestamp_ms, "source": "media"})
        # Weather/GPS/speed remain absent until telemetry or a trusted model exists.
        yield frame


__all__ = ["extract_metadata"]
