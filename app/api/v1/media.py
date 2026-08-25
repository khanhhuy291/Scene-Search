"""Keyframe thumbnail and clip delivery.

Objects are proxied rather than presigned. A presigned URL is shorter code, but
it requires the browser to reach the object store directly -- which it usually
cannot, since the store is not on the public network -- and it puts a credentialed
URL into page source and browser history. Proxying keeps the URL relative, stable
across credential rotation, and cacheable by the browser.

The route is keyed by **point id**, never by object key. Accepting a key from the
client would make this an open read of any object in the bucket, including
originals; resolving the key from the indexed keyframe means a caller can only
ever fetch something the index already published (ADR-0003).

Clips are served with byte-range support, which is not optional for this product.
A ``<video>`` element seeks by requesting a byte range; served without one it has
to download the whole object before it can show anything, and it cannot seek at
all. Since the point of opening a result is to land on the matched second of a
20 MB clip, a rangeless response reads to the user as a video player that does
not work.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from loguru import logger
from minio.error import MinioException

from api.deps import get_current_user
from core.config import get_settings
from search.catalog import get_catalog

router = APIRouter(
    prefix="/media",
    tags=["media"],
    dependencies=[Depends(get_current_user)],
)

# Thumbnails are immutable: the key contains the point id and the frame number, so
# a given URL's bytes never change and the browser can keep them.
_CACHE_CONTROL = "private, max-age=86400, immutable"

# Streamed rather than buffered, so a request for one second of video does not
# hold a whole clip in memory. 256 KiB keeps the syscall count reasonable without
# making the first chunk slow to arrive.
_CLIP_CHUNK_BYTES = 1 << 18

# Only a single range is honoured. Multipart ranges exist in the spec and no
# browser video element sends them, so parsing them would be untested code on a
# path that matters.
_RANGE_HEADER = re.compile(r"^bytes=(\d*)-(\d*)$")

_media_client = None


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


def _bucket_for_key(object_key: str) -> str:
    """Resolve only publishable media buckets; never route a request to raw storage."""

    settings = get_settings().minio
    if not settings.scene_media_endpoint:
        # Locally ingested media is privacy-verified before it is written to the
        # derived bucket. Originals in the raw bucket are never served.
        return settings.derived_bucket
    key = object_key.lstrip("/")
    if key.startswith(("videos/", "raw_videos/", "frames/", "thumbnails/", "keyframes/")):
        return settings.derived_bucket
    return settings.scene_media_bucket


def reset_media_client() -> None:
    """Drop the cached client so settings changes take effect (used by tests)."""

    global _media_client
    _media_client = None


def get_media_store():
    """Return the object-store client used for indexed thumbnails and clips."""

    return _client()


def read_media_object(object_key: str) -> bytes:
    """Fetch one indexed media object by key (blocking)."""

    return _read_object(_bucket_for_key(object_key), object_key)


def _read_object(bucket: str, object_key: str) -> bytes:
    """Fetch an object's bytes. Blocking, so callers offload it to a thread."""

    response = None
    try:
        response = _client().get_object(bucket, object_key)
        return response.read()
    finally:
        if response is not None:
            response.close()
            response.release_conn()


async def _fetch(object_key: str, *, content_type: str) -> Response:
    bucket = _bucket_for_key(object_key)
    # The MinIO SDK is synchronous: run the fetch on a worker thread so a slow
    # object store cannot stall the event loop for every other request, search
    # included. Mirrors the sync-generator handling in ``_stream``.
    try:
        payload = await asyncio.to_thread(_read_object, bucket, object_key)
    except MinioException as exc:
        # A missing object is the normal case for a keyframe indexed before its
        # derivative was written, so it is a 404 rather than a server fault.
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
    catalog = get_catalog()
    keyframe = catalog.get(point_id)
    if keyframe is None or not keyframe.has_thumbnail:
        from infrastructure.qdrant import get_qdrant_client

        await catalog.ensure_loaded(get_qdrant_client(), force=True)
        keyframe = catalog.get(point_id)

    if keyframe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown keyframe")
    if not keyframe.thumbnail_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This keyframe has no thumbnail yet",
        )
    return await _fetch(keyframe.thumbnail_key, content_type="image/jpeg")


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Resolve a Range header to inclusive byte offsets.

    Returns None when the header is absent or unparseable, which means "send the
    whole object": an unsatisfiable *syntax* is defined to be ignored, unlike an
    out-of-bounds range, which the caller rejects with 416.
    """

    match = _RANGE_HEADER.match(header.strip())
    if match is None:
        return None
    raw_start, raw_end = match.group(1), match.group(2)

    if not raw_start and not raw_end:
        return None
    if not raw_start:
        # A suffix range: the last N bytes.
        length = min(int(raw_end), size)
        return size - length, size - 1

    start = int(raw_start)
    end = int(raw_end) if raw_end else size - 1
    return start, min(end, size - 1)


def _stream(bucket: str, object_key: str, *, offset: int, length: int) -> Iterator[bytes]:
    """Yield an object's bytes in chunks, closing the connection on any exit.

    A sync generator on purpose: Starlette runs one in a worker thread, so the
    blocking reads do not stall the event loop. An async generator here would
    block every other request -- including search -- for the length of the
    download.
    """

    response = None
    try:
        response = _client().get_object(bucket, object_key, offset=offset, length=length)
        while True:
            chunk = response.read(_CLIP_CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    finally:
        if response is not None:
            response.close()
            response.release_conn()


@router.get("/clip/{point_id}", summary="Video containing a keyframe")
async def get_clip(point_id: str, request: Request) -> Response:
    catalog = get_catalog()
    keyframe = catalog.get(point_id)
    if keyframe is None or not keyframe.video_key:
        from infrastructure.qdrant import get_qdrant_client

        await catalog.ensure_loaded(get_qdrant_client(), force=True)
        keyframe = catalog.get(point_id)

    if keyframe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown keyframe")
    if not keyframe.video_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This keyframe has no clip yet"
        )

    bucket = _bucket_for_key(keyframe.video_key)
    # stat_object is a blocking round trip to the object store; offload it so it
    # does not stall the event loop before streaming even begins.
    try:
        stat = await asyncio.to_thread(_client().stat_object, bucket, keyframe.video_key)
        size = stat.size or 0
    except MinioException as exc:
        logger.debug("Clip {key} unavailable: {error}", key=keyframe.video_key, error=exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Media object is not available"
        ) from exc
    except OSError as exc:
        logger.warning("Media store unreachable for {key}", key=keyframe.video_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Media store is unreachable"
        ) from exc

    headers = {
        # Announced even on a full response: without it the player assumes seeking
        # is impossible and disables the scrub bar.
        "Accept-Ranges": "bytes",
        "Cache-Control": _CACHE_CONTROL,
    }

    requested = _parse_range(request.headers.get("range", ""), size) if size else None
    if requested is None:
        return StreamingResponse(
            _stream(bucket, keyframe.video_key, offset=0, length=size),
            media_type="video/mp4",
            headers={**headers, "Content-Length": str(size)},
        )

    start, end = requested
    if start >= size or start > end:
        # 416 must carry the real size, or the player cannot correct itself.
        return Response(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{size}"},
        )

    length = end - start + 1
    return StreamingResponse(
        _stream(bucket, keyframe.video_key, offset=start, length=length),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type="video/mp4",
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        },
    )


__all__ = [
    "_bucket_for_key",
    "get_media_store",
    "read_media_object",
    "reset_media_client",
    "router",
]
