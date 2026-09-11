"""Media endpoints: keyframe thumbnails and video clips.

ADR-0003: Video clips and extracted keyframes are served through this API rather
than linked directly to object storage. This keeps the internal MinIO endpoint
off the public internet, avoids browser Mixed-Content blocks when the API is
behind TLS, and provides a single place to enforce authentication and access
control on media assets.

ADR-0004: All media assets are keyed by ``point_id`` (UUID string), matching
the point identifiers used across Qdrant, the ingestion manifests, and the
frontend.
"""

from __future__ import annotations

import asyncio
import mimetypes
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from loguru import logger
from minio.error import MinioException

from api.deps import get_current_user_optional
from core.config import get_settings
from search.catalog import get_catalog

router = APIRouter(
    prefix="/media",
    tags=["media"],
    dependencies=[Depends(get_current_user_optional)],
)

# Thumbnails are immutable: the key contains the point id and the frame number, so
# a given URL's bytes never change and the browser can keep them.
_CACHE_CONTROL = "private, max-age=86400, immutable"

# Streamed rather than buffered. 256 KiB delivers lightning-fast start and minimal buffer wait.
_CLIP_CHUNK_BYTES = 256 * 1024

# In-memory fast cache for resolved media locations: point_id -> (client, bucket_or_path, key, size, content_type, is_disk)
_media_loc_cache: dict[str, tuple[Any, str | Path, str, int, str, bool]] = {}

# In-memory fast cache for initial video stream chunks: point_id or vid_{video_id} -> bytes
_video_chunk_cache: dict[str, bytes] = {}
_MAX_VIDEO_CHUNK_CACHE_ENTRIES = 128


def _put_video_chunk_cache(key: str, data: bytes) -> None:
    """Store initial video chunk in memory cache with simple FIFO eviction."""
    if len(_video_chunk_cache) >= _MAX_VIDEO_CHUNK_CACHE_ENTRIES:
        try:
            oldest_k = next(iter(_video_chunk_cache))
            _video_chunk_cache.pop(oldest_k, None)
        except Exception:
            _video_chunk_cache.clear()
    _video_chunk_cache[key] = data


# Only a single range is honoured. Multipart ranges exist in the spec and no
# browser video element sends them, so parsing them would be untested code on a
# path that matters.
_RANGE_HEADER = re.compile(r"^bytes=(\d*)-(\d*)$")

_media_client = None
_remote_media_client = None


def _client():
    """Client for the store the index's media lives in.

    Built lazily so that a deployment with no media store still serves search
    results -- with null thumbnails -- rather than failing at import.
    """

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


def _remote_viettech_client():
    """Fallback client for remote Viettech cloud MinIO store."""
    global _remote_media_client
    if _remote_media_client is None:
        from minio import Minio

        _remote_media_client = Minio(
            endpoint="bucket.viettech.fit",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=True,
        )
    return _remote_media_client


def _candidate_buckets_for_key(object_key: str) -> list[str]:
    """Return prioritized candidate buckets for a given media object key."""
    settings = get_settings().minio
    key = object_key.lstrip("/")
    if key.startswith(("videos/", "raw_videos/")):
        candidates = [
            settings.raw_bucket,
            settings.derived_bucket,
            settings.scene_media_bucket,
            settings.bucket,
            "aic2026",
            "scenesearch-raw",
            "scenesearch-derived",
        ]
    else:
        candidates = [
            settings.derived_bucket,
            settings.raw_bucket,
            settings.scene_media_bucket,
            settings.bucket,
            "aic2026",
            "scenesearch-derived",
            "scenesearch-raw",
        ]
    seen: set[str] = set()
    return [b for b in candidates if b and not (b in seen or seen.add(b))]


def _candidate_keys_for_video(video_key: str | None, video_id: str | None) -> list[str]:
    """Return prioritized filename variants for a video object key."""
    candidates: list[str] = []
    if video_key:
        cleaned = video_key.strip().lstrip("/")
        candidates.append(cleaned)
        path = PurePosixPath(cleaned)
        stem = path.stem
        filename = path.name
        candidates.append(f"videos/{filename}")
        candidates.append(f"raw_videos/{filename}")
        candidates.append(f"raw/{filename}")
        candidates.append(filename)
        for suffix in (".mov", ".mp4", ".MOV", ".MP4", ".webm", ".mkv"):
            candidates.append(f"videos/{stem}{suffix}")
            candidates.append(f"raw_videos/{stem}{suffix}")
            candidates.append(f"raw/{stem}{suffix}")
            candidates.append(f"{stem}{suffix}")
    if video_id:
        vid = str(video_id).strip()
        candidates.append(f"{vid}.mov")
        candidates.append(f"{vid}.mp4")
        candidates.append(f"raw/{vid}/source.mp4")
        candidates.append(f"raw/{vid}/source.mov")
        candidates.append(f"raw/{vid}.mp4")
        candidates.append(f"raw/{vid}.mov")
        candidates.append(f"videos/{vid}.mov")
        candidates.append(f"videos/{vid}.mp4")
        candidates.append(f"raw_videos/{vid}.mov")
        candidates.append(f"raw_videos/{vid}.mp4")
    seen: set[str] = set()
    return [k for k in candidates if k and not (k in seen or seen.add(k))]


def _bucket_for_key(object_key: str) -> str:
    """Resolve only publishable media buckets; never route a request to raw storage."""

    settings = get_settings().minio
    if not settings.scene_media_endpoint:
        return settings.derived_bucket
    key = object_key.lstrip("/")
    if key.startswith(("videos/", "raw_videos/", "frames/", "thumbnails/", "keyframes/")):
        return settings.derived_bucket
    return settings.scene_media_bucket


def reset_media_client() -> None:
    """Drop the cached client and location caches so settings changes take effect (used by tests)."""

    global _media_client, _remote_media_client
    _media_client = None
    _remote_media_client = None
    _media_loc_cache.clear()
    _thumbnail_cache.clear()
    _video_chunk_cache.clear()


def get_media_store():
    """Return the object-store client used for indexed thumbnails and clips."""

    return _client()


# In-memory LRU fast cache for thumbnail payloads: (point_id or object_key) -> bytes
_thumbnail_cache: dict[str, bytes] = {}
_MAX_THUMBNAIL_CACHE_ENTRIES = 2048


def _put_thumbnail_cache(key: str, data: bytes) -> None:
    """Store data in memory cache with simple FIFO/LRU eviction."""
    if len(_thumbnail_cache) >= _MAX_THUMBNAIL_CACHE_ENTRIES:
        try:
            oldest_k = next(iter(_thumbnail_cache))
            _thumbnail_cache.pop(oldest_k, None)
        except Exception:
            _thumbnail_cache.clear()
    _thumbnail_cache[key] = data


def _candidate_keys_for_thumbnail(object_key: str) -> list[str]:
    """Return prioritized candidate object keys for a thumbnail."""
    cleaned = object_key.strip().lstrip("/")
    candidates = [cleaned]
    if cleaned.startswith("frames/"):
        candidates.append(cleaned[7:])
    elif cleaned.startswith("thumbnails/"):
        candidates.append(cleaned[11:])
    else:
        candidates.append(f"frames/{cleaned}")
        candidates.append(f"thumbnails/{cleaned}")
    seen = set()
    return [k for k in candidates if k and not (k in seen or seen.add(k))]


def read_media_object(object_key: str) -> bytes:
    """Fetch one indexed media object by key (blocking)."""

    return _read_object(_bucket_for_key(object_key), object_key)


def _read_object(bucket: str, object_key: str) -> bytes:
    """Fetch an object's bytes from in-memory cache, local disk, or MinIO."""

    if object_key in _thumbnail_cache:
        return _thumbnail_cache[object_key]

    is_video = any(
        object_key.lower().endswith(ext) for ext in (".mp4", ".mov", ".webm", ".mkv")
    ) or object_key.startswith(("videos/", "raw_videos/", "raw/"))
    if is_video:
        candidate_keys = _candidate_keys_for_video(object_key, None)
    else:
        candidate_keys = _candidate_keys_for_thumbnail(object_key)

    # 1. Check local filesystem disk (0ms)
    for key_cand in candidate_keys:
        for base in [
            Path("/app/data"),
            Path("data"),
            Path("/data"),
            Path("/app/data/driving-video-object-tracking"),
            Path("data/driving-video-object-tracking"),
        ]:
            disk_path = base / key_cand
            if disk_path.is_file():
                payload = disk_path.read_bytes()
                if not is_video:
                    _put_thumbnail_cache(object_key, payload)
                return payload

    # 2. Check MinIO stores (primary client direct)
    settings = get_settings().minio
    primary_client = _client()
    raw_bucket = settings.raw_bucket or "scenesearch-raw-vinai"
    derived_bucket = settings.derived_bucket or "scencesearch-frames-vinai"
    candidate_buckets = (
        [raw_bucket, derived_bucket, settings.scene_media_bucket, settings.bucket]
        if is_video
        else [derived_bucket, raw_bucket, settings.scene_media_bucket, settings.bucket]
    )
    seen_b = set()
    candidate_buckets = [b for b in candidate_buckets if b and not (b in seen_b or seen_b.add(b))]

    last_exc: Exception | None = None
    for candidate_key in candidate_keys:
        for b in candidate_buckets:
            response = None
            try:
                response = primary_client.get_object(b, candidate_key)
                payload = response.read()
                if not is_video:
                    _put_thumbnail_cache(object_key, payload)
                return payload
            except Exception as exc:
                last_exc = exc
                continue
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()

    # Fallback to remote Viettech client only if primary misses
    if (
        settings.endpoint != "bucket.viettech.fit"
        and settings.scene_media_endpoint != "bucket.viettech.fit"
    ):
        try:
            remote_cl = _remote_viettech_client()
            for candidate_key in candidate_keys[:4]:
                for b in candidate_buckets[:2]:
                    response = None
                    try:
                        response = remote_cl.get_object(b, candidate_key)
                        payload = response.read()
                        if not is_video:
                            _put_thumbnail_cache(object_key, payload)
                        return payload
                    except Exception as exc:
                        last_exc = exc
                        continue
                    finally:
                        if response is not None:
                            response.close()
                            response.release_conn()
        except Exception:
            pass

    if last_exc:
        raise last_exc
    raise MinioException(f"Object {object_key} not found")


async def _fetch(object_key: str, *, content_type: str) -> Response:
    bucket = _bucket_for_key(object_key)
    try:
        payload = await asyncio.to_thread(_read_object, bucket, object_key)
    except MinioException as exc:
        logger.debug("Media object {key} unavailable: {error}", key=object_key, error=exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media object is not available"
        ) from exc
    except OSError as exc:
        logger.warning("Media store unreachable for {key}: {error}", key=object_key, error=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media store is unreachable",
        ) from exc

    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": _CACHE_CONTROL},
    )


@router.get("/thumbnail/{point_id}", summary="Keyframe thumbnail")
async def get_thumbnail(point_id: str) -> Response:
    # 0. Check in-memory cache directly (0.01ms response time!)
    if point_id in _thumbnail_cache:
        return Response(
            content=_thumbnail_cache[point_id],
            media_type="image/jpeg",
            headers={"Cache-Control": _CACHE_CONTROL},
        )

    catalog = get_catalog()
    keyframe = catalog.get(point_id)
    if keyframe is None or not keyframe.has_thumbnail:
        from infrastructure.qdrant import get_qdrant_client

        # Fast direct single-point lookup from Qdrant (5ms)
        qclient = get_qdrant_client()
        try:
            settings = get_settings()
            records = await qclient.retrieve(
                collection_name=settings.qdrant.collection,
                ids=[point_id],
                with_payload=True,
            )
            if records and records[0].payload:
                payload = records[0].payload
                tkey = payload.get("thumbnail_key") or payload.get("minio_path")
                if not tkey and payload.get("video_id") and payload.get("frame_id") is not None:
                    tkey = f"{payload['video_id']}/frame_{int(payload['frame_id']):05d}.jpg"
                if tkey:
                    resp = await _fetch(tkey, content_type="image/jpeg")
                    if resp.body:
                        _put_thumbnail_cache(point_id, resp.body)
                    return resp
        except Exception:
            pass

        # Fallback to catalog ensure_loaded
        await catalog.ensure_loaded(get_qdrant_client())
        keyframe = catalog.get(point_id)

    if keyframe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown keyframe")
    if not keyframe.thumbnail_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This keyframe has no thumbnail yet",
        )
    resp = await _fetch(keyframe.thumbnail_key, content_type="image/jpeg")
    if resp.body:
        _put_thumbnail_cache(point_id, resp.body)
    return resp


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Resolve a Range header to inclusive byte offsets."""

    match = _RANGE_HEADER.match(header.strip())
    if match is None:
        return None
    raw_start, raw_end = match.group(1), match.group(2)

    if not raw_start and not raw_end:
        return None
    if not raw_start:
        length = min(int(raw_end), size)
        return size - length, size - 1

    start = int(raw_start)
    end = int(raw_end) if raw_end else size - 1
    return start, min(end, size - 1)


def _stream(client, bucket: str, object_key: str, *, offset: int, length: int) -> Iterator[bytes]:
    """Yield an object's bytes in chunks from MinIO."""

    response = None
    try:
        response = client.get_object(bucket, object_key, offset=offset, length=length)
        if hasattr(response, "stream"):
            yield from response.stream(_CLIP_CHUNK_BYTES)
        elif hasattr(response, "read"):
            data = response.read()
            for i in range(0, len(data), _CLIP_CHUNK_BYTES):
                yield data[i : i + _CLIP_CHUNK_BYTES]
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def _stream_file(file_path: Path, *, offset: int, length: int) -> Iterator[bytes]:
    """Yield a file's bytes in chunks from local filesystem."""

    with open(file_path, "rb") as f:
        f.seek(offset)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(_CLIP_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


async def _fast_stat_check(client, bucket: str, key: str):
    """Test if object exists with stat_object."""
    try:
        stat = await asyncio.to_thread(client.stat_object, bucket, key)
        return client, bucket, key, stat
    except Exception:
        return None


async def _resolve_media_location_fast(
    point_id: str | None,
    video_id: str | None,
    initial_key: str | None = None,
) -> tuple[Any, str | Path, str, int, str, bool]:
    """Blazing-fast parallel candidate resolver with two-way caching."""
    # 0. Check cache
    if point_id and point_id in _media_loc_cache:
        return _media_loc_cache[point_id]
    if video_id and f"vid_{video_id}" in _media_loc_cache:
        return _media_loc_cache[f"vid_{video_id}"]

    candidate_keys = _candidate_keys_for_video(initial_key, video_id)

    # 1. Local disk check (0ms)
    for key_cand in candidate_keys:
        for base in [
            Path("/app/data"),
            Path("data"),
            Path("/data"),
            Path("/app/data/driving-video-object-tracking"),
            Path("data/driving-video-object-tracking"),
        ]:
            disk_path = base / key_cand
            if disk_path.is_file():
                stat_res = disk_path.stat()
                size = stat_res.st_size
                content_type = mimetypes.guess_type(str(disk_path))[0] or "video/mp4"
                res = (None, str(disk_path), key_cand, size, content_type, True)
                if point_id:
                    _media_loc_cache[point_id] = res
                if video_id:
                    _media_loc_cache[f"vid_{video_id}"] = res
                return res

    # 2. Priority check: Primary storage client first (GCS / MinIO direct - 20ms)
    settings = get_settings().minio
    primary_client = _client()
    raw_bucket = settings.raw_bucket or "scenesearch-raw-vinai"
    derived_bucket = settings.derived_bucket or "scencesearch-frames-vinai"
    candidate_buckets = [raw_bucket, derived_bucket, settings.scene_media_bucket, settings.bucket]
    seen_b = set()
    candidate_buckets = [b for b in candidate_buckets if b and not (b in seen_b or seen_b.add(b))]

    top_keys = candidate_keys[:6]
    primary_tasks = []
    for k in top_keys:
        for b in candidate_buckets[:2]:
            primary_tasks.append(_fast_stat_check(primary_client, b, k))

    if primary_tasks:
        primary_results = await asyncio.gather(*primary_tasks, return_exceptions=True)
        for r in primary_results:
            if r and isinstance(r, tuple) and len(r) == 4 and r[3] is not None:
                cl, b, k, stat = r
                size = stat.size or 0
                content_type = mimetypes.guess_type(k)[0] or "video/mp4"
                res = (cl, b, k, size, content_type, False)
                if point_id:
                    _media_loc_cache[point_id] = res
                if video_id:
                    _media_loc_cache[f"vid_{video_id}"] = res
                return res

    # 3. Secondary check: Remaining primary candidate keys
    remaining_keys = candidate_keys[6:]
    if remaining_keys or len(candidate_buckets) > 2:
        sec_tasks = []
        for k in remaining_keys:
            for b in candidate_buckets[:2]:
                sec_tasks.append(_fast_stat_check(primary_client, b, k))
        for k in top_keys:
            for b in candidate_buckets[2:]:
                sec_tasks.append(_fast_stat_check(primary_client, b, k))
        if sec_tasks:
            sec_results = await asyncio.gather(*sec_tasks, return_exceptions=True)
            for r in sec_results:
                if r and isinstance(r, tuple) and len(r) == 4 and r[3] is not None:
                    cl, b, k, stat = r
                    size = stat.size or 0
                    content_type = mimetypes.guess_type(k)[0] or "video/mp4"
                    res = (cl, b, k, size, content_type, False)
                    if point_id:
                        _media_loc_cache[point_id] = res
                    if video_id:
                        _media_loc_cache[f"vid_{video_id}"] = res
                    return res

    # 4. Fallback check: Remote Viettech store (only if primary completely misses)
    if (
        settings.endpoint != "bucket.viettech.fit"
        and settings.scene_media_endpoint != "bucket.viettech.fit"
    ):
        try:
            remote_cl = _remote_viettech_client()
            remote_tasks = [
                _fast_stat_check(remote_cl, b, k)
                for k in top_keys[:4]
                for b in candidate_buckets[:2]
            ]
            remote_results = await asyncio.gather(*remote_tasks, return_exceptions=True)
            for r in remote_results:
                if r and isinstance(r, tuple) and len(r) == 4 and r[3] is not None:
                    cl, b, k, stat = r
                    size = stat.size or 0
                    content_type = mimetypes.guess_type(k)[0] or "video/mp4"
                    res = (cl, b, k, size, content_type, False)
                    if point_id:
                        _media_loc_cache[point_id] = res
                    if video_id:
                        _media_loc_cache[f"vid_{video_id}"] = res
                    return res
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Video media object is not available",
    )


def _stream_with_cached_prefix(
    cached_prefix: bytes,
    client: Any,
    bucket: str,
    object_key: str,
    *,
    offset: int,
    length: int,
    is_disk: bool = False,
    disk_path: Path | None = None,
) -> Iterator[bytes]:
    """Yield from pre-cached RAM prefix first, then stream remaining bytes from source."""
    prefix_len = len(cached_prefix)
    if offset < prefix_len:
        prefix_start = offset
        prefix_end = min(prefix_len, offset + length)
        chunk = cached_prefix[prefix_start:prefix_end]
        yield chunk
        rem_offset = prefix_len
        rem_length = length - len(chunk)
    else:
        rem_offset = offset
        rem_length = length

    if rem_length > 0:
        if is_disk and disk_path:
            yield from _stream_file(disk_path, offset=rem_offset, length=rem_length)
        else:
            yield from _stream(client, bucket, object_key, offset=rem_offset, length=rem_length)


def _build_streaming_response(
    resolved_client: Any,
    resolved_target: str | Path,
    resolved_key: str,
    size: int,
    content_type: str,
    is_disk: bool,
    request: Request,
    cache_key: str | None = None,
) -> Response:
    """Build partial range (206) or full (200) streaming response with instant RAM prefix cache."""
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": _CACHE_CONTROL,
    }
    requested = _parse_range(request.headers.get("range", ""), size) if size else None
    cached_prefix = _video_chunk_cache.get(cache_key) if cache_key else None

    # Fast-path 1: Range request within pre-cached memory buffer
    if requested is not None:
        start, end = requested
        if start >= size or start > end:
            return Response(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{size}"},
            )
        length = end - start + 1
        if cached_prefix and start == 0 and end < len(cached_prefix):
            return Response(
                content=cached_prefix[start : end + 1],
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                media_type=content_type,
                headers={
                    **headers,
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Content-Length": str(length),
                },
            )
        # Stream using cached prefix if available
        if cached_prefix and start < len(cached_prefix):
            return StreamingResponse(
                _stream_with_cached_prefix(
                    cached_prefix,
                    resolved_client,
                    str(resolved_target),
                    resolved_key,
                    offset=start,
                    length=length,
                    is_disk=is_disk,
                    disk_path=Path(resolved_target) if is_disk else None,
                ),
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                media_type=content_type,
                headers={
                    **headers,
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Content-Length": str(length),
                },
            )

    # Standard range streaming
    if is_disk:
        disk_path = Path(resolved_target)
        if requested is None:
            return StreamingResponse(
                _stream_file(disk_path, offset=0, length=size),
                media_type=content_type,
                headers={**headers, "Content-Length": str(size)},
            )
        start, end = requested
        length = end - start + 1
        return StreamingResponse(
            _stream_file(disk_path, offset=start, length=length),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=content_type,
            headers={
                **headers,
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(length),
            },
        )
    else:
        if requested is None:
            return StreamingResponse(
                _stream(resolved_client, str(resolved_target), resolved_key, offset=0, length=size),
                media_type=content_type,
                headers={**headers, "Content-Length": str(size)},
            )
        start, end = requested
        length = end - start + 1
        return StreamingResponse(
            _stream(
                resolved_client, str(resolved_target), resolved_key, offset=start, length=length
            ),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=content_type,
            headers={
                **headers,
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(length),
            },
        )


@router.get("/clip/{point_id}", summary="Video containing a keyframe")
async def get_clip(point_id: str, request: Request) -> Response:
    """Stream a video containing the given keyframe point."""
    if point_id in _media_loc_cache:
        resolved_client, resolved_target, resolved_key, size, content_type, is_disk = (
            _media_loc_cache[point_id]
        )
        return _build_streaming_response(
            resolved_client,
            resolved_target,
            resolved_key,
            size,
            content_type,
            is_disk,
            request,
            cache_key=point_id,
        )

    catalog = get_catalog()
    keyframe = catalog.get(point_id)
    if keyframe is None or not keyframe.video_key:
        from infrastructure.qdrant import get_qdrant_client

        try:
            await catalog.ensure_loaded(get_qdrant_client(), force=True)
            keyframe = catalog.get(point_id)
        except Exception:
            pass

    if keyframe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown keyframe")

    initial_key = keyframe.video_key or (
        f"videos/{keyframe.video_id}.mov" if keyframe.video_id else ""
    )
    if not initial_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This keyframe has no clip yet"
        )

    (
        resolved_client,
        resolved_target,
        resolved_key,
        size,
        content_type,
        is_disk,
    ) = await _resolve_media_location_fast(point_id, keyframe.video_id, initial_key)

    return _build_streaming_response(
        resolved_client,
        resolved_target,
        resolved_key,
        size,
        content_type,
        is_disk,
        request,
        cache_key=point_id,
    )


@router.get("/video/{video_id}", summary="Full video stream by video ID")
async def get_video_by_id(video_id: str, request: Request) -> Response:
    """Stream a video directly by its video_id."""
    cache_key = f"vid_{video_id}"
    if cache_key in _media_loc_cache:
        resolved_client, resolved_target, resolved_key, size, content_type, is_disk = (
            _media_loc_cache[cache_key]
        )
        return _build_streaming_response(
            resolved_client,
            resolved_target,
            resolved_key,
            size,
            content_type,
            is_disk,
            request,
            cache_key=cache_key,
        )

    (
        resolved_client,
        resolved_target,
        resolved_key,
        size,
        content_type,
        is_disk,
    ) = await _resolve_media_location_fast(None, video_id, None)

    return _build_streaming_response(
        resolved_client,
        resolved_target,
        resolved_key,
        size,
        content_type,
        is_disk,
        request,
        cache_key=cache_key,
    )


async def precache_point_thumbnail(point_id: str, thumbnail_key: str | None = None) -> None:
    """Pre-fetch and store a single thumbnail in the memory cache."""
    if point_id in _thumbnail_cache:
        return
    try:
        if not thumbnail_key:
            catalog = get_catalog()
            kf = catalog.get(point_id)
            if kf:
                thumbnail_key = kf.thumbnail_key
        if thumbnail_key:
            data = await asyncio.to_thread(
                _read_object, _bucket_for_key(thumbnail_key), thumbnail_key
            )
            if data:
                _put_thumbnail_cache(point_id, data)
    except Exception:
        pass


async def precache_video_stream(
    point_id: str | None,
    video_id: str | None,
    initial_key: str | None = None,
    chunk_size: int = _CLIP_CHUNK_BYTES,
) -> None:
    """Pre-resolve location and fetch initial video chunk into memory cache."""
    cache_keys = []
    if point_id:
        cache_keys.append(point_id)
    if video_id:
        cache_keys.append(f"vid_{video_id}")

    if all(k in _video_chunk_cache for k in cache_keys if k):
        return

    try:
        (
            resolved_client,
            resolved_target,
            resolved_key,
            size,
            content_type,
            is_disk,
        ) = await _resolve_media_location_fast(point_id, video_id, initial_key)
        fetch_len = min(chunk_size, size) if size else chunk_size
        data = None
        if is_disk:
            disk_path = Path(resolved_target)
            with open(disk_path, "rb") as f:
                data = f.read(fetch_len)
        else:
            response = await asyncio.to_thread(
                resolved_client.get_object,
                str(resolved_target),
                resolved_key,
                offset=0,
                length=fetch_len,
            )
            data = response.read()
            response.close()
            response.release_conn()

        if data:
            for k in cache_keys:
                _put_video_chunk_cache(k, data)
    except Exception:
        pass


async def precache_search_results(results: list[Any], top_k: int = 5) -> None:
    """Pre-fetch thumbnails and initial video stream chunks for search results concurrently."""
    tasks = []
    for i, r in enumerate(results[:20]):
        pid = getattr(r, "id", None) or (r.get("id") if isinstance(r, dict) else None)
        tkey = getattr(r, "thumbnail_key", None) or (
            r.get("thumbnail_key") if isinstance(r, dict) else None
        )
        vid = getattr(r, "video_id", None) or (r.get("video_id") if isinstance(r, dict) else None)
        vkey = getattr(r, "video_key", None) or (
            r.get("video_key") if isinstance(r, dict) else None
        )

        if pid:
            tasks.append(precache_point_thumbnail(str(pid), str(tkey) if tkey else None))

        # Pre-cache initial video stream for Top-K scenes
        if i < top_k and (pid or vid):
            tasks.append(
                precache_video_stream(
                    str(pid) if pid else None,
                    str(vid) if vid else None,
                    str(vkey) if vkey else None,
                )
            )

        moments = getattr(r, "matched_moments", []) or (
            r.get("matched_moments", []) if isinstance(r, dict) else []
        )
        for m in moments[:4]:
            mid = getattr(m, "id", None) or (m.get("id") if isinstance(m, dict) else None)
            mtkey = getattr(m, "thumbnail_key", None) or (
                m.get("thumbnail_key") if isinstance(m, dict) else None
            )
            if mid:
                tasks.append(precache_point_thumbnail(str(mid), str(mtkey) if mtkey else None))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def precache_startup_thumbnails(limit: int = 100) -> None:
    """Pre-cache initial keyframe thumbnails and video locations during server startup."""
    try:
        catalog = get_catalog()
        keyframes = list(catalog._by_id.values())[:limit]
        tasks = []
        for i, kf in enumerate(keyframes):
            if kf.point_id and kf.thumbnail_key:
                tasks.append(precache_point_thumbnail(kf.point_id, kf.thumbnail_key))
            if kf.video_id:
                if i < 10:
                    tasks.append(precache_video_stream(kf.point_id, kf.video_id, kf.video_key))
                else:
                    tasks.append(
                        _resolve_media_location_fast(kf.point_id, kf.video_id, kf.video_key)
                    )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Pre-cached {count} media objects in memory cache", count=len(tasks))
    except Exception as exc:
        logger.debug("Startup media pre-cache skipped: {error}", error=exc)


__all__ = [
    "get_clip",
    "get_video_by_id",
    "get_media_store",
    "get_thumbnail",
    "precache_point_thumbnail",
    "precache_search_results",
    "precache_startup_thumbnails",
    "precache_video_stream",
    "read_media_object",
    "reset_media_client",
    "router",
]
