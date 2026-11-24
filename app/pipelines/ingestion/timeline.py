"""Source timestamps shared by decoding and anonymized playback."""

from __future__ import annotations

from dataclasses import dataclass


def frame_timestamp_ms(
    time_s: float | None, *, index: int, rate: float, previous_ms: int | None
) -> int:
    """Preserve source PTS with the playback encoder's millisecond repair rule."""
    source_ms = round((time_s if time_s is not None else index / rate) * 1000)
    earliest = previous_ms + 1 if previous_ms is not None else 0
    return max(earliest, source_ms)


@dataclass(frozen=True)
class VideoProbe:
    start_ms: int
    end_ms: int | None
    duration_source: str
    time_base: str | None


@dataclass
class DecodeTimeline:
    """EOF information updated while consuming the existing decode pass."""

    end_ms: int | None = None
    duration_source: str = "unavailable"
