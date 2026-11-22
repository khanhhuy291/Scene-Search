"""Zip verified thumbnails and a JSONL manifest for selected moments."""

from __future__ import annotations

import asyncio
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from loguru import logger

from api.v1.media import read_media_object
from core.privacy import is_anonymized_thumbnail
from infrastructure.qdrant import get_qdrant_client
from schemas.datasets import DatasetExportRequest
from search.catalog import get_catalog


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)
    return cleaned[:80] or "item"


async def build_export_zip(request: DatasetExportRequest) -> Path:
    catalog = get_catalog()
    await catalog.ensure_loaded(get_qdrant_client())

    missing: list[str] = []
    resolved_items = []

    for item in request.items:
        frame = catalog.get(item.point_id)
        if frame is None:
            missing.append(f"{item.point_id}: unknown keyframe")
            continue
        resolved_items.append((item, frame))

    if not resolved_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the selected moments are in the live index",
        )

    header = {
        "type": "provenance",
        "dataset_id": request.dataset_id,
        "title": request.title,
        "queries": request.queries,
        "model_version": request.model_version,
        "item_count": len(resolved_items),
        "video_count": 0,
        "contents": ["keyframes"],
        "exported_at": datetime.now(UTC).isoformat(),
    }
    manifest_lines = [json.dumps(header, separators=(",", ":"))]
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
                    "thumbnail_object": (
                        frame.thumbnail_key
                        if is_anonymized_thumbnail(frame.thumbnail_key)
                        else None
                    ),
                    "video_object": None,
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
        resolved_items,
        missing,
    )


def _write_archive(
    tmp_path: Path,
    manifest_lines: list[str],
    resolved_items: list,
    missing: list[str],
) -> Path:
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.jsonl", "\n".join(manifest_lines) + "\n")

        for _item, frame in resolved_items:
            if not is_anonymized_thumbnail(frame.thumbnail_key):
                missing.append(f"{frame.point_id}: anonymized thumbnail unavailable")
                continue
            try:
                payload = read_media_object(frame.thumbnail_key)
            except HTTPException as exc:
                logger.debug(
                    "Export skipped thumb {key}: {error}",
                    key=frame.thumbnail_key,
                    error=exc,
                )
                missing.append(f"{frame.point_id}: thumbnail unavailable")
                continue
            archive.writestr(
                f"thumbnails/{_safe_name(frame.point_id)}.jpg",
                payload,
            )

        if missing:
            archive.writestr("missing.txt", "\n".join(missing) + "\n")

    return tmp_path
