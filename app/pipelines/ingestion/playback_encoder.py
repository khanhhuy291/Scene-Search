"""Encode a silent, anonymized MP4 from the full source timeline."""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from ml.anonymize import anonymize_frame
from pipelines.ingestion.timeline import frame_timestamp_ms
from pipelines.ingestion.video_reader import apply_display_rotation, display_rotation_ccw

if TYPE_CHECKING:
    from pathlib import Path

    from core.config import VideoSettings
    from ml.anonymize import BlurRegionDetector

_TIME_BASE = Fraction(1, 1000)


def _preview_size(width: int, height: int, max_edge: int) -> tuple[int, int]:
    scale = min(1.0, max_edge / max(width, height))
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


def write_anonymized_playback(
    source: Path, destination: Path, detector: BlurRegionDetector, settings: VideoSettings
) -> None:
    import av

    timestamps: list[int] = []
    with (
        av.open(str(source)) as incoming,
        av.open(str(destination), "w", options={"movflags": "+faststart"}) as output,
    ):
        video = incoming.streams.video[0]
        rate = video.average_rate or video.guessed_rate or Fraction(30, 1)
        stream = output.add_stream("libx264", rate=rate)
        stream.pix_fmt = "yuv420p"
        stream.time_base = _TIME_BASE
        stream.codec_context.time_base = _TIME_BASE
        stream.options = {"crf": str(settings.preview_crf), "preset": "veryfast"}

        for index, frame in enumerate(incoming.decode(video=0)):
            with apply_display_rotation(
                frame.to_image(), display_rotation_ccw(frame, video)
            ) as image:
                result = anonymize_frame(image, detector=detector)
                if not result.blurred:
                    raise ValueError(
                        f"Playback anonymization failed on frame {index}: {result.error}"
                    )
                with result.image as redacted:
                    if not timestamps:
                        stream.width, stream.height = _preview_size(
                            *redacted.size, settings.preview_max_edge
                        )
                    with redacted.resize((stream.width, stream.height)) as resized:
                        encoded = av.VideoFrame.from_image(resized)

            timestamp = frame_timestamp_ms(
                frame.time,
                index=index,
                rate=float(rate),
                previous_ms=timestamps[-1] if timestamps else None,
            )
            timestamps.append(timestamp)
            encoded.pts = timestamp
            encoded.time_base = _TIME_BASE
            output.mux(stream.encode(encoded))

        if not timestamps:
            raise ValueError("Source has no frames for anonymized playback")
        output.mux(stream.encode())

    with av.open(str(destination)) as playback:
        for frame, timestamp in zip(playback.decode(video=0), timestamps, strict=True):
            if frame.time is None or abs(round(frame.time * 1000) - timestamp) > 1:
                raise ValueError("Anonymized playback timeline could not be verified")
