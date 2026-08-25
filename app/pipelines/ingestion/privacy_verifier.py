"""Fail-closed verification gate, separate from anonymization."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from pipelines.common.types import FrameRecord


def verified_frames(frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]:
    """Publish only frames for which the anonymization pass completed."""
    for frame in frames:
        if frame.privacy_status != "verified":
            frame.image.close()
            continue
        yield frame


__all__ = ["verified_frames"]
