"""Acquire a raw MinIO object into bounded temporary local storage."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

from infrastructure.minio import MinIOStorage
from pipelines.common.context import PipelineContext
from pipelines.common.errors import (
    RetryableVideoAcquireError,
    VideoAcquireError,
    VideoDecodeError,
    VideoValidationError,
)
from pipelines.common.types import FrameRecord


async def acquire_video(ctx: PipelineContext, raw_storage: MinIOStorage) -> Path:
    if not ctx.raw_minio_key.strip():
        raise VideoAcquireError("Video has no raw MinIO object key", stage="acquire")
    suffix = Path(ctx.raw_minio_key).suffix or ".bin"
    destination = ctx.open_temp_dir() / f"input{suffix.lower()}"
    try:
        await asyncio.to_thread(raw_storage.download_file, ctx.raw_minio_key, destination)
    except Exception as exc:
        raise RetryableVideoAcquireError("Unable to download raw video", stage="acquire") from exc
    if not destination.is_file():
        raise VideoAcquireError("Raw video download produced no file", stage="acquire")
    return destination


def validate_video(path: Path, *, max_duration_s: float, max_pixels: int) -> None:
    """Probe the acquired media before expensive decoding or inference."""
    try:
        import av
    except ImportError as exc:
        raise VideoValidationError("PyAV is not installed", stage="validate") from exc
    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise VideoValidationError("Media has no video stream", stage="validate")
            stream = container.streams.video[0]
            width, height = int(stream.width or 0), int(stream.height or 0)
            if width <= 0 or height <= 0:
                raise VideoValidationError("Media has invalid dimensions", stage="validate")
            if width * height > max_pixels:
                raise VideoValidationError(
                    f"Video resolution {width}x{height} exceeds the configured pixel limit",
                    stage="validate",
                )
            duration_s = None
            if stream.duration is not None and stream.time_base is not None:
                duration_s = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration_s = float(container.duration) / 1_000_000
            if duration_s is not None and duration_s > max_duration_s:
                raise VideoValidationError(
                    f"Video duration {duration_s:.2f}s exceeds the {max_duration_s:.2f}s limit",
                    stage="validate",
                )
    except VideoValidationError:
        raise
    except Exception as exc:
        raise VideoValidationError("Unable to validate video", stage="validate") from exc


def decode_video(path: Path) -> Iterator[FrameRecord]:
    """Decode sequentially without materializing or dumping frames."""
    try:
        import av
    except ImportError as exc:
        raise VideoDecodeError("PyAV is not installed", stage="decode") from exc
    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise VideoDecodeError("Media has no video stream", stage="decode")
            stream = container.streams.video[0]
            fallback_fps = float(stream.average_rate or stream.guessed_rate or 1)
            for index, frame in enumerate(container.decode(video=0)):
                timestamp_s = float(frame.time) if frame.time is not None else index / fallback_fps
                timestamp_ms = max(0, round(timestamp_s * 1000))
                yield FrameRecord(
                    timestamp_ms=timestamp_ms,
                    frame_index=index,
                    image=frame.to_image().convert("RGB"),
                    covers_start_ms=timestamp_ms,
                    covers_end_ms=timestamp_ms,
                )
    except VideoDecodeError:
        raise
    except Exception as exc:
        raise VideoDecodeError("Unable to decode video", stage="decode") from exc


__all__ = ["acquire_video", "decode_video", "validate_video"]
