"""Serve anonymized thumbnails and playback from the derived object store."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from loguru import logger
from minio.error import MinioException

from api.deps import get_current_user_optional
from core.config import get_settings
from core.privacy import is_anonymized_playback, is_anonymized_thumbnail
from infrastructure.minio import MinIOError, MinIOStorage, get_derived_storage
from infrastructure.qdrant import get_qdrant_client
from repositories import corpus
from search.catalog import get_catalog

router = APIRouter(
    prefix="/media",
    tags=["media"],
    dependencies=[Depends(get_current_user_optional)],
)

_media_client = None
_thumbnail_cache: dict[str, bytes] = {}
_MAX_THUMBNAIL_CACHE_ENTRIES = 2048
_BYTE_RANGE = re.compile(r"bytes=([0-9]{0,20})-([0-9]{0,20})")
_STREAM_CHUNK_SIZE = 256 * 1024


def _client():
    global _media_client
    if _media_client is None:
        settings = get_settings().minio
        endpoint = settings.scene_media_endpoint or settings.endpoint
        access = settings.access_key.get_secret_value()
        secret = settings.secret_key.get_secret_value()
        secure = settings.scene_media_secure if settings.scene_media_endpoint else settings.secure
        if settings.scene_media_console:
            from infrastructure.minio_console import MinIOConsoleStore

            _media_client = MinIOConsoleStore(endpoint, access, secret, secure=secure)
        else:
            from minio import Minio

            _media_client = Minio(
                endpoint=endpoint,
                access_key=access,
                secret_key=secret,
                secure=secure,
                region=settings.region,
            )
    return _media_client


def reset_media_client() -> None:
    global _media_client
    _media_client = None
    _thumbnail_cache.clear()


def get_media_store():
    return _client()


def read_media_object(object_key: str) -> bytes:
    """Read a published anonymized thumbnail."""
    if not is_anonymized_thumbnail(object_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media unavailable")
    try:
        return get_derived_storage().read_object(object_key)
    except MinIOError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media unavailable"
        ) from exc


async def _thumbnail_bytes(object_key: str) -> bytes:
    if object_key in _thumbnail_cache:
        return _thumbnail_cache[object_key]
    payload = await asyncio.to_thread(read_media_object, object_key)
    if len(_thumbnail_cache) >= _MAX_THUMBNAIL_CACHE_ENTRIES:
        _thumbnail_cache.pop(next(iter(_thumbnail_cache)))
    _thumbnail_cache[object_key] = payload
    return payload


@router.get("/thumbnail/{point_id}", summary="Anonymized keyframe thumbnail")
async def get_thumbnail(point_id: str) -> Response:
    keyframe = get_catalog().get(point_id)
    object_key = keyframe.thumbnail_key if keyframe else None
    if not is_anonymized_thumbnail(object_key):
        client = get_qdrant_client()
        try:
            records = await client.retrieve(
                collection_name=get_settings().qdrant.collection,
                ids=[point_id],
                with_payload=True,
            )
        except Exception as exc:
            logger.debug("Thumbnail lookup failed for {point}: {error}", point=point_id, error=exc)
            records = []
        object_key = (records[0].payload or {}).get("thumbnail_key") if records else None
    if not is_anonymized_thumbnail(object_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Anonymized thumbnail unavailable"
        )
    return Response(
        content=await _thumbnail_bytes(object_key),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-cache"},
    )


def _playback_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Anonymized playback unavailable",
        headers={"Cache-Control": "no-store"},
    )


def _playback_range(header: str, size: int) -> tuple[int, int] | None:
    match = _BYTE_RANGE.fullmatch(header)
    if not match:
        return None
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return None

    if start_text:
        start = int(start_text)
        end = min(int(end_text), size - 1) if end_text else size - 1
    else:
        start = max(0, size - int(end_text))
        end = size - 1

    if start > end:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="Requested range is outside playback",
            headers={"Content-Range": f"bytes */{size}", "Cache-Control": "no-store"},
        )
    return start, end


def _playback_bytes(storage: MinIOStorage, key: str, offset: int, length: int) -> Iterator[bytes]:
    response = storage.client.get_object(storage.bucket, key, offset=offset, length=length)
    try:
        while chunk := response.read(_STREAM_CHUNK_SIZE):
            yield chunk
    finally:
        response.close()
        response.release_conn()


@router.get("/clip/{point_id}", summary="Anonymized video containing the keyframe")
async def get_clip(point_id: str, request: Request) -> Response:
    keyframe = get_catalog().get(point_id)
    if keyframe is not None:
        return await get_video_by_id(keyframe.video_id, request)

    try:
        point_uuid = UUID(point_id)
        records = await get_qdrant_client().retrieve(
            collection_name=get_settings().qdrant.collection,
            ids=[str(point_uuid)],
            with_payload=True,
        )
    except Exception as exc:
        raise _playback_unavailable() from exc
    video_id = (records[0].payload or {}).get("video_id") if records else None
    if not isinstance(video_id, str):
        raise _playback_unavailable()
    return await get_video_by_id(video_id, request)


@router.get("/video/{video_id}", summary="Anonymized full video")
async def get_video_by_id(video_id: str, request: Request) -> Response:
    try:
        video_uuid = UUID(video_id)
    except ValueError as exc:
        raise _playback_unavailable() from exc
    video = await corpus.get_video_for_pipeline(video_uuid)
    if video is None or not video.preview_blurred or video.ingestion_status == "deleting":
        raise _playback_unavailable()

    key = video.preview_object_key
    if not is_anonymized_playback(key) or not key.startswith(f"videos/{video_uuid}/"):
        raise _playback_unavailable()

    storage = get_derived_storage()
    try:
        stat = await asyncio.to_thread(storage.client.stat_object, storage.bucket, key)
    except MinioException as exc:
        raise _playback_unavailable() from exc
    size = stat.size or 0
    if size <= 0:
        raise _playback_unavailable()

    requested = _playback_range(request.headers.get("range", ""), size)
    start, end = requested or (0, size - 1)
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-cache",
        "Content-Length": str(length),
    }
    if requested is not None:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _playback_bytes(storage, key, start, length),
        media_type="video/mp4",
        status_code=(
            status.HTTP_206_PARTIAL_CONTENT if requested is not None else status.HTTP_200_OK
        ),
        headers=headers,
    )


async def precache_point_thumbnail(point_id: str, thumbnail_key: str | None = None) -> None:
    if thumbnail_key is None:
        keyframe = get_catalog().get(point_id)
        thumbnail_key = keyframe.thumbnail_key if keyframe else None
    if is_anonymized_thumbnail(thumbnail_key):
        await _thumbnail_bytes(thumbnail_key)


async def precache_search_results(results: list[Any]) -> None:
    tasks = []
    for result in results[:20]:
        point_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        if point_id:
            tasks.append(precache_point_thumbnail(str(point_id)))
        moments = (
            result.get("matched_moments", [])
            if isinstance(result, dict)
            else getattr(result, "matched_moments", [])
        )
        for moment in (moments or [])[:4]:
            point_id = moment.get("id") if isinstance(moment, dict) else getattr(moment, "id", None)
            if point_id:
                tasks.append(precache_point_thumbnail(str(point_id)))
    await asyncio.gather(*tasks, return_exceptions=True)


async def precache_startup_thumbnails(limit: int = 100) -> None:
    keyframes = list(get_catalog()._by_id.values())[:limit]
    await asyncio.gather(
        *(precache_point_thumbnail(frame.point_id, frame.thumbnail_key) for frame in keyframes),
        return_exceptions=True,
    )


__all__ = [
    "get_clip",
    "get_media_store",
    "get_thumbnail",
    "get_video_by_id",
    "precache_point_thumbnail",
    "precache_search_results",
    "precache_startup_thumbnails",
    "read_media_object",
    "reset_media_client",
    "router",
]
