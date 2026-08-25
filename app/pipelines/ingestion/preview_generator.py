"""Generate deterministic previews exclusively from verified anonymized frames."""

from __future__ import annotations

import asyncio
import math
from fractions import Fraction
from pathlib import Path

from infrastructure.minio import MinIOStorage
from pipelines.common.context import PipelineContext
from pipelines.common.errors import RetryablePersistenceError
from pipelines.common.types import SceneRecord


def _preview_size(width: int, height: int, max_edge: int) -> tuple[int, int]:
    scale = min(1.0, max_edge / max(width, height))
    # yuv420p requires even dimensions.
    resized_width = max(2, int(width * scale) // 2 * 2)
    resized_height = max(2, int(height * scale) // 2 * 2)
    return resized_width, resized_height


def _write_video_preview(ctx: PipelineContext, scene: SceneRecord, path: Path) -> None:
    try:
        import av
    except ImportError as exc:
        raise RuntimeError("PyAV is required to encode scene previews") from exc

    settings = ctx.settings.video
    source = scene.keyframes[0].image
    width, height = _preview_size(source.width, source.height, settings.preview_max_edge)
    rate = Fraction(str(settings.preview_fps)).limit_denominator(1000)
    duration_s = max(1.0 / float(rate), (scene.end_ms - scene.start_ms) / 1000)
    output_frames = max(1, math.ceil(duration_s * float(rate)))

    with av.open(str(path), mode="w") as container:
        stream = container.add_stream(settings.preview_codec, rate=rate)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": str(settings.preview_crf)}

        source_index = 0
        for output_index in range(output_frames):
            timestamp_ms = scene.start_ms + round(output_index * 1000 / float(rate))
            while (
                source_index + 1 < len(scene.keyframes)
                and scene.keyframes[source_index + 1].timestamp_ms <= timestamp_ms
            ):
                source_index += 1
            image = scene.keyframes[source_index].image.convert("RGB")
            if image.size != (width, height):
                resized = image.resize((width, height))
                image.close()
                image = resized
            try:
                frame = av.VideoFrame.from_image(image)
            finally:
                image.close()
            frame.pts = output_index
            frame.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


async def generate_previews(
    ctx: PipelineContext, scenes: list[SceneRecord], derived_storage: MinIOStorage
) -> list[str]:
    uploaded: list[str] = []
    root = ctx.open_temp_dir() / "previews"
    root.mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        if scene.privacy_status != "verified" or not scene.keyframes:
            continue
        thumbnail_key = f"thumbnails/{ctx.video_id}/scenes/{scene.scene_id}/preview.jpg"
        preview_key = f"videos/{ctx.video_id}/scenes/{scene.scene_id}/preview.mp4"
        thumbnail_path = root / f"{scene.scene_id}.jpg"
        preview_path = root / f"{scene.scene_id}.mp4"
        thumbnail = scene.keyframes[len(scene.keyframes) // 2].image.convert("RGB")
        try:
            thumbnail.save(
                thumbnail_path,
                format="JPEG",
                quality=ctx.settings.dataset.thumbnail_quality,
                optimize=True,
            )
        finally:
            thumbnail.close()
        try:
            await asyncio.to_thread(_write_video_preview, ctx, scene, preview_path)
            await asyncio.to_thread(
                derived_storage.upload_file,
                thumbnail_key,
                thumbnail_path,
                content_type="image/jpeg",
            )
            uploaded.append(thumbnail_key)
            await asyncio.to_thread(
                derived_storage.upload_file,
                preview_key,
                preview_path,
                content_type="video/mp4",
            )
        except Exception as exc:
            raise RetryablePersistenceError(
                "Unable to upload scene preview", stage="preview_generation"
            ) from exc
        scene.thumbnail_key = thumbnail_key
        scene.preview_key = preview_key
        uploaded.append(preview_key)
    return uploaded


__all__ = ["generate_previews"]
