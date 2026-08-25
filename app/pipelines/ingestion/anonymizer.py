"""Privacy anonymization stage."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ml.anonymize import BlurRegionDetector, anonymize_frame
from pipelines.common.types import FrameRecord


def anonymize_frames(
    frames: Iterable[FrameRecord], detector: BlurRegionDetector
) -> Iterator[FrameRecord]:
    for frame in frames:
        result = anonymize_frame(frame.image, detector=detector)
        if result.image is not frame.image:
            frame.image.close()
        frame.image = result.image
        frame.privacy_region_count = result.region_count
        frame.privacy_status = "verified" if result.blurred else "failed"
        if result.error:
            frame.metadata["privacy_error"] = result.error
        yield frame


__all__ = ["anonymize_frames"]
