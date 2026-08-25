"""Tracking interface and deterministic no-model baseline."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol

from pipelines.common.types import FrameRecord


class ObjectTracker(Protocol):
    def track(self, frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]: ...


class PassthroughTracker:
    """Preserves detector-provided track IDs; does not fabricate tracks."""

    def track(self, frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]:
        yield from frames


__all__ = ["ObjectTracker", "PassthroughTracker"]
