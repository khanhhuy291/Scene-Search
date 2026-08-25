"""Zip an engineer-selected set of indexed clips + a JSONL manifest."""

from __future__ import annotations

import asyncio
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from loguru import logger
from minio.error import MinioException

from api.v1.media import read_media_object
from infrastructure.qdrant import get_qdrant_client
from schemas.datasets import DatasetExportRequest
from search.catalog import get_catalog

MAX_UNIQUE_CLIPS = 40


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)
    return cleaned[:80] or "item"


def _suffix(object_key: str, default: str) -> str:
    name = object_key.rsplit("/", 1)[-1]
    if "." in name:
        return "." + name.rsplit(".", 1)[-1].lower()
    return default


async def build_export_zip(request: DatasetExportRequest) -> Path:
    catalog = get_catalog()
    await catalog.ensure_loaded(get_qdrant_client())

    unique_clips: dict[str, str] = {}
    missing: list[str] = []
    resolved_items = []

    for item in request.items:
        frame = catalog.get(item.point_id)
        if frame is None:
            missing.append(f"{item.point_id}: unknown keyframe")
            continue
        resolved_items.append((item, frame))
        if frame.video_key and frame.video_key not in unique_clips:
            unique_clips[frame.video_key] = frame.video_id

    if len(unique_clips) > MAX_UNIQUE_CLIPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This dataset has {len(unique_clips)} unique videos; "
                f"export is capped at {MAX_UNIQUE_CLIPS}. Split the set and retry."
            ),
        )
    if not resolved_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the selected moments are in the live index",
        )

    videos = [
        {
            "video_id": video_id,
            "object_key": object_key,
            "moment_count": sum(1 for _, frame in resolved_items if frame.video_id == video_id),
        }
        for object_key, video_id in unique_clips.items()
    ]
    header = {
        "type": "provenance",
        "dataset_id": request.dataset_id,
        "title": request.title,
        "queries": request.queries,
        "model_version": request.model_version,
        "item_count": len(resolved_items),
        "video_count": len(videos),
        "contents": ["keyframes", "videos"],
        "exported_at": datetime.now(UTC).isoformat(),
    }
    manifest_lines = [json.dumps(header, separators=(",", ":"))]
    for video in videos:
        manifest_lines.append(json.dumps({"type": "video", **video}, separators=(",", ":")))
    for item, frame in resolved_items:
        manifest_lines.append(
            json.dumps(
                {
                    "type": "keyframe",
                    "scene_id": frame.point_id,
                    "video_id": frame.video_id,
                    "ts_start_s": (
                        item.ts_start_s if item.ts_start_s is not None else frame.timestamp_s
                    ),
                    "ts_end_s": item.ts_end_s,
                    "caption": item.caption or frame.caption,
                    "query": item.query,
                    "required_concepts": item.required_concepts,
                    "excluded_concepts": item.excluded_concepts,
                    "weather": item.weather or frame.weather,
                    "time_of_day": item.time_of_day or frame.time_of_day,
                    "objects": item.objects,
                    "thumbnail_object": frame.thumbnail_key,
                    "video_object": frame.video_key,
                },
                separators=(",", ":"),
            )
        )

    with tempfile.NamedTemporaryFile(prefix="dataset-export-", suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    return await asyncio.to_thread(
        _write_archive,
        tmp_path,
        manifest_lines,
        unique_clips,
        resolved_items,
        missing,
    )


def _write_archive(
    tmp_path: Path,
    manifest_lines: list[str],
    unique_clips: dict[str, str],
    resolved_items: list,
    missing: list[str],
) -> Path:
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.jsonl", "\n".join(manifest_lines) + "\n")

        for object_key, video_id in unique_clips.items():
            try:
                payload = read_media_object(object_key)
            except (MinioException, OSError, HTTPException) as exc:
                logger.info("Export skipped clip {key}: {error}", key=object_key, error=exc)
                missing.append(f"{video_id}: clip unavailable ({object_key})")
                continue
            filename = f"videos/{_safe_name(video_id)}{_suffix(object_key, '.mp4')}"
            archive.writestr(filename, payload, compress_type=zipfile.ZIP_STORED)

        for _item, frame in resolved_items:
            if not frame.thumbnail_key:
                continue
            try:
                payload = read_media_object(frame.thumbnail_key)
            except (MinioException, OSError, HTTPException) as exc:
                logger.debug(
                    "Export skipped thumb {key}: {error}",
                    key=frame.thumbnail_key,
                    error=exc,
                )
                continue
            archive.writestr(
                f"thumbnails/{_safe_name(frame.point_id)}{_suffix(frame.thumbnail_key, '.jpg')}",
                payload,
            )

        if missing:
            archive.writestr("missing.txt", "\n".join(missing) + "\n")

    return tmp_path
