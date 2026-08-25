"""Embedding-based near-duplicate removal for sampled frames."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from pipelines.common.types import FrameRecord


@dataclass
class DedupStats:
    seen: int = 0
    kept: int = 0

    @property
    def dropped(self) -> int:
        return self.seen - self.kept

    @property
    def drop_ratio(self) -> float:
        return self.dropped / self.seen if self.seen else 0.0


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def filter_near_duplicates(
    frames: Iterable[FrameRecord],
    *,
    enabled: bool,
    threshold: float,
    stats: DedupStats | None = None,
) -> Iterator[FrameRecord]:
    stats = stats or DedupStats()
    previous: FrameRecord | None = None
    for frame in frames:
        stats.seen += 1
        if frame.embedding is None:
            raise ValueError("Frame must be embedded before deduplication")
        duplicate = (
            enabled
            and previous is not None
            and previous.embedding is not None
            and cosine(previous.embedding, frame.embedding) >= threshold
        )
        if duplicate:
            previous.covers_end_ms = frame.covers_end_ms or frame.timestamp_ms
            frame.image.close()
            continue
        stats.kept += 1
        previous = frame
        yield frame


__all__ = ["DedupStats", "cosine", "filter_near_duplicates"]
