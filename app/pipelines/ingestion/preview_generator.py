"""Publish anonymized playback and scene thumbnails."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from core.privacy import PLAYBACK_VERSION, THUMBNAIL_VERSION
from infrastructure.minio import MinIOStorage
from pipelines.common.context import PipelineContext
from pipelines.common.errors import RetryablePersistenceError
from pipelines.common.types import SceneRecord
from pipelines.ingestion.playback_encoder import write_anonymized_playback

if TYPE_CHECKING:
    from pathlib import Path

    from ml.anonymize import BlurRegionDetector


async def generate_previews(
    ctx: PipelineContext,
    scenes: list[SceneRecord],
    derived_storage: MinIOStorage,
    *,
    source_video: Path,
    detector: BlurRegionDetector,
) -> list[str]:
    uploaded: list[str] = []
    root = ctx.open_temp_dir() / "media"
    root.mkdir(parents=True, exist_ok=True)
    playback_path = root / "playback.mp4"
    playback_key = f"videos/{ctx.video_id}/playback-{PLAYBACK_VERSION}/{ctx.job_id}.mp4"
    try:
        await asyncio.to_thread(
            write_anonymized_playback, source_video, playback_path, detector, ctx.settings.video
        )
        await asyncio.to_thread(
            derived_storage.upload_file, playback_key, playback_path, content_type="video/mp4"
        )
        uploaded.append(playback_key)
        for scene in scenes:
            thumbnail_key = (
                f"videos/{ctx.video_id}/segments/{scene.scene_id}/"
                f"thumbnail-{THUMBNAIL_VERSION}/{ctx.job_id}.jpg"
            )
            thumbnail_path = root / f"{scene.scene_id}.jpg"
            frame = scene.keyframes[len(scene.keyframes) // 2]
            if frame.privacy_status != "verified" or frame.display_image is None:
                raise ValueError("Thumbnail frame has no verified derivative")
            thumbnail = frame.display_image.convert("RGB")
            try:
                thumbnail.thumbnail((ctx.settings.dataset.thumbnail_max_edge,) * 2)
                thumbnail.save(
                    thumbnail_path, format="JPEG", quality=ctx.settings.dataset.thumbnail_quality
                )
            finally:
                thumbnail.close()
            await asyncio.to_thread(
                derived_storage.upload_file,
                thumbnail_key,
                thumbnail_path,
                content_type="image/jpeg",
            )
            uploaded.append(thumbnail_key)
            scene.thumbnail_key = thumbnail_key
            scene.preview_key = playback_key
        return uploaded
    except Exception as exc:
        for key in uploaded:
            with suppress(Exception):
                await asyncio.to_thread(derived_storage.delete_object, key)
        raise RetryablePersistenceError(
            "Unable to publish anonymized playback and thumbnails", stage="preview_generation"
        ) from exc


__all__ = ["generate_previews"]
