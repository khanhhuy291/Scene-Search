"""Acquire a raw MinIO object into bounded temporary local storage."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from PIL import Image

from infrastructure.minio import MinIOStorage
from pipelines.common.context import PipelineContext
from pipelines.common.errors import (
    RetryableVideoAcquireError,
    VideoAcquireError,
    VideoDecodeError,
    VideoValidationError,
)
from pipelines.common.types import FrameRecord


def _snap_rotation_degrees(value: float) -> int:
    """Normalize to {0, 90, 180, 270} for stable PIL transpose behavior."""
    degrees = int(round(float(value))) % 360
    return int(round(degrees / 90.0) * 90) % 360


def display_rotation_ccw(frame: Any, stream: Any) -> int:
    """Return counter-clockwise degrees needed so decoded pixels match display.

    Prefers PyAV ``VideoFrame.rotation`` (DISPLAYMATRIX, already CCW). Falls back
    to the legacy ``rotate`` stream tag, which FFmpeg/Android store as clockwise.
    """
    frame_rotation = getattr(frame, "rotation", None)
    if frame_rotation:
        try:
            snapped = _snap_rotation_degrees(frame_rotation)
            if snapped:
                return snapped
        except (TypeError, ValueError):
            pass

    metadata = getattr(stream, "metadata", None) or {}
    rotate_tag = metadata.get("rotate")
    if rotate_tag is None:
        return 0
    try:
        clockwise = _snap_rotation_degrees(float(rotate_tag))
    except (TypeError, ValueError):
        return 0
    return 0 if clockwise == 0 else (360 - clockwise) % 360


def apply_display_rotation(image: Image.Image, degrees_ccw: int) -> Image.Image:
    """Bake display orientation into pixel buffers used for derived assets."""
    snapped = _snap_rotation_degrees(degrees_ccw)
    if snapped == 0:
        return image
    rotated = image.rotate(snapped, expand=True)
    if rotated is not image:
        image.close()
    return rotated


async def acquire_video(ctx: PipelineContext, raw_storage: MinIOStorage) -> Path:
    candidates = []
    if ctx.raw_minio_key and ctx.raw_minio_key.strip():
        candidates.append(ctx.raw_minio_key.strip())
    vid = str(ctx.video_id).strip()
    for ext in (".mp4", ".mov", ".MP4", ".MOV", ".webm", ".mkv"):
        candidates.append(f"{vid}{ext}")
        candidates.append(f"raw/{vid}/source{ext}")
        candidates.append(f"videos/{vid}{ext}")

    seen = set()
    unique_candidates = [k for k in candidates if k and not (k in seen or seen.add(k))]

    if not unique_candidates:
        raise VideoAcquireError("Video has no raw MinIO object key", stage="acquire")

    suffix = Path(unique_candidates[0]).suffix or ".mp4"
    destination = ctx.open_temp_dir() / f"input{suffix.lower()}"

    last_exc = None
    for cand in unique_candidates:
        try:
            await asyncio.to_thread(raw_storage.download_file, cand, destination)
            if destination.is_file() and destination.stat().st_size > 0:
                ctx.raw_minio_key = cand
                return destination
        except Exception as exc:
            last_exc = exc
            continue

    raise RetryableVideoAcquireError("Unable to download raw video", stage="acquire") from last_exc


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
                image = frame.to_image().convert("RGB")
                image = apply_display_rotation(image, display_rotation_ccw(frame, stream))
                yield FrameRecord(
                    timestamp_ms=timestamp_ms,
                    frame_index=index,
                    image=image,
                    covers_start_ms=timestamp_ms,
                    covers_end_ms=timestamp_ms,
                )
    except VideoDecodeError:
        raise
    except Exception as exc:
        raise VideoDecodeError("Unable to decode video", stage="decode") from exc


__all__ = [
    "acquire_video",
    "apply_display_rotation",
    "decode_video",
    "display_rotation_ccw",
    "validate_video",
]
