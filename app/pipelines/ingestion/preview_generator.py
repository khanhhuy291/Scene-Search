"""Publish anonymized playback and scene thumbnails."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from core.privacy import PLAYBACK_VERSION, is_anonymized_thumbnail
from infrastructure.minio import MinIOStorage
from pipelines.common.context import PipelineContext
from pipelines.common.errors import RetryablePersistenceError
from pipelines.common.types import FrameRecord, IndexedKeyframe, SceneRecord
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
    keyframes: list[IndexedKeyframe],
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
        for frame in keyframes:
            path = root / "keyframes" / f"{frame.keyframe_id}.jpg"
            if not path.is_file() or not is_anonymized_thumbnail(frame.thumbnail_key):
                raise ValueError("Indexed keyframe has no staged verified thumbnail")
            await asyncio.to_thread(
                derived_storage.upload_file, frame.thumbnail_key, path, content_type="image/jpeg"
            )
            uploaded.append(frame.thumbnail_key)
        for scene in scenes:
            if (
                not is_anonymized_thumbnail(scene.thumbnail_key)
                or scene.thumbnail_key not in uploaded
            ):
                raise ValueError("Scene references an unpublished keyframe thumbnail")
            scene.preview_key = playback_key
        return uploaded
    except Exception as exc:
        for key in uploaded:
            with suppress(Exception):
                await asyncio.to_thread(derived_storage.delete_object, key)
        raise RetryablePersistenceError(
            "Unable to publish anonymized playback and thumbnails", stage="preview_generation"
        ) from exc


def stage_keyframe_thumbnail(
    ctx: PipelineContext, keyframe: IndexedKeyframe, frame: FrameRecord
) -> None:
    if frame.privacy_status != "verified" or frame.display_image is None:
        raise ValueError("Indexed thumbnail requires a verified privacy derivative")
    root = ctx.open_temp_dir() / "media" / "keyframes"
    root.mkdir(parents=True, exist_ok=True)
    with frame.display_image.convert("RGB") as thumbnail:
        thumbnail.thumbnail((ctx.settings.dataset.thumbnail_max_edge,) * 2)
        thumbnail.save(
            root / f"{keyframe.keyframe_id}.jpg",
            format="JPEG",
            quality=ctx.settings.dataset.thumbnail_quality,
        )


__all__ = ["generate_previews", "stage_keyframe_thumbnail"]
