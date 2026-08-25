"""Temporal behavior interface with an honest empty baseline."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol

from pipelines.common.types import FrameRecord


class TemporalBehaviorDetector(Protocol):
    def detect(self, frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]: ...


class NoopBehaviorDetector:
    """Returns no inferred behavior until reliable tracks are available."""

    def detect(self, frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]:
        yield from frames


__all__ = ["NoopBehaviorDetector", "TemporalBehaviorDetector"]
