"""Multi-tier Image Cache for Keyframe Retrieval and Visual Reranking.

Features:
- L1 In-Memory RAM Cache: Instant ~0ms access during evaluation / serving.
- L2 Redis Cache: Shared across processes (gracefully bypassed if Redis is unavailable).
- L3 MinIO Storage: Fetches from bucket.viettech.fit when not in cache.
"""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Sequence
from pathlib import Path

from loguru import logger
from PIL import Image

from core.config import get_settings


class KeyframeImageCache:
    """High-performance multi-tier image cache (RAM -> Redis -> MinIO)."""

    def __init__(self, ttl_seconds: int = 86400 * 7, max_edge: int = 384) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_edge = max_edge
        self._ram_cache: dict[str, Image.Image] = {}
        self._redis_available: bool = True

    def _cache_key(self, video_id: str, frame_name: str) -> str:
        clean_fname = Path(frame_name).name if frame_name else "unknown.jpg"
        return f"keyframe:img:{video_id}:{clean_fname}"

    def _resize_and_compress(self, img_bytes: bytes) -> tuple[Image.Image, str]:
        """Resize image to thumbnail (max_edge) and encode as base64 jpeg."""
        with Image.open(io.BytesIO(img_bytes)) as img:
            img = img.convert("RGB")
            img.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            compressed_bytes = buf.getvalue()
            b64_str = base64.b64encode(compressed_bytes).decode("ascii")
            return img.copy(), b64_str

    async def get_images_batch(
        self,
        items: Sequence[tuple[str, str]],  # List of (video_id, frame_name)
        *,
        bucket: str | None = None,
    ) -> list[Image.Image | None]:
        """Batch retrieve images with RAM -> Redis -> MinIO tiered fallback."""
        if not items:
            return []

        results: list[Image.Image | None] = [None] * len(items)
        missing_indices: list[int] = []

        # 1. Check L1 RAM Cache
        for i, (vid, fname) in enumerate(items):
            key = self._cache_key(vid, fname)
            if key in self._ram_cache:
                results[i] = self._ram_cache[key]
            else:
                missing_indices.append(i)

        if not missing_indices:
            return results

        # 2. Check L2 Redis Cache (if available)
        if self._redis_available:
            try:
                from infrastructure.redis import get_redis_client

                redis = get_redis_client()
                missing_keys = [
                    self._cache_key(items[idx][0], items[idx][1]) for idx in missing_indices
                ]
                cached_values = await redis.mget(missing_keys)

                still_missing = []
                for m_idx, val in zip(missing_indices, cached_values):
                    if val:
                        try:
                            raw_b64 = base64.b64decode(val)
                            img = Image.open(io.BytesIO(raw_b64)).convert("RGB")
                            results[m_idx] = img
                            self._ram_cache[self._cache_key(items[m_idx][0], items[m_idx][1])] = img
                        except Exception:
                            still_missing.append(m_idx)
                    else:
                        still_missing.append(m_idx)
                missing_indices = still_missing
            except Exception as exc:
                logger.debug(f"Redis cache bypassed: {exc}")
                self._redis_available = False

        if not missing_indices:
            return results

        # 3. Fetch from L3 MinIO Storage for missing items
        logger.info(f"Downloading {len(missing_indices)} missing keyframes from MinIO...")

        from infrastructure.minio import MinIOStorage

        settings = get_settings().minio
        target_bucket = (
            bucket if (bucket and bucket != "scenesearch-derived") else settings.derived_bucket
        )
        storage = MinIOStorage(settings, bucket=target_bucket)

        async def _fetch_one_minio(idx: int) -> None:
            vid, fname = items[idx]
            clean_name = Path(fname).name if fname else f"frame_{idx:05d}.jpg"
            key = self._cache_key(vid, fname)

            try:

                def _sync_get():
                    candidates = [
                        f"{vid}/{clean_name}",
                        f"frames/{vid}/{clean_name}",
                    ]
                    for obj_name in candidates:
                        try:
                            response = storage.client.get_object(storage.bucket, obj_name)
                            try:
                                return response.read()
                            finally:
                                response.close()
                                response.release_conn()
                        except Exception:
                            continue
                    response = storage.client.get_object(storage.bucket, f"{vid}/{clean_name}")
                    try:
                        return response.read()
                    finally:
                        response.close()
                        response.release_conn()

                raw_data = await asyncio.to_thread(_sync_get)
                img, b64_str = self._resize_and_compress(raw_data)
                results[idx] = img
                self._ram_cache[key] = img

                # Optionally write back to Redis in background
                if self._redis_available:
                    try:
                        from infrastructure.redis import get_redis_client

                        await get_redis_client().setex(key, self.ttl_seconds, b64_str)
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning(f"Failed to download {key} from MinIO: {exc}")
                results[idx] = None

        # Fetch concurrently with semaphore limit
        sem = asyncio.Semaphore(32)

        async def _bounded_fetch(idx: int):
            async with sem:
                await _fetch_one_minio(idx)

        await asyncio.gather(
            *[_bounded_fetch(idx) for idx in missing_indices], return_exceptions=True
        )
        return results


_image_cache: KeyframeImageCache | None = None


def get_image_cache() -> KeyframeImageCache:
    global _image_cache
    if _image_cache is None:
        _image_cache = KeyframeImageCache()
    return _image_cache
