"""Publish legacy raw videos to the derived media bucket.

Legacy frame-level Qdrant points contain ``minio_path`` for the thumbnail but
often omit ``minio_video_key``.  Their source video still exists in the raw
bucket, which the media API deliberately refuses to serve.  This migration
copies an explicitly approved source object to the derived bucket and stamps
the resulting key onto every point for the same video.

The command is a dry-run unless both ``--apply`` and
``--confirm-publish-raw`` are supplied.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error
from qdrant_client import AsyncQdrantClient

from core.config import get_settings
from infrastructure.qdrant import get_qdrant_client


@dataclass
class LegacyVideo:
    video_id: str
    point_ids: list[str | int] = field(default_factory=list)
    payload_keys: set[str] = field(default_factory=set)


def _object_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lstrip("/")
    if not key or "://" in key or key.startswith(("./", "../")):
        return None
    return key


def _payload_video_keys(payload: dict[str, Any]) -> Iterable[str]:
    for name in ("minio_video_key", "video_key", "raw_minio_key"):
        key = _object_key(payload.get(name))
        if key:
            yield key
    # Some legacy exports put an object key in video_path; absolute host paths
    # are intentionally ignored because they are meaningless in production.
    video_path = _object_key(payload.get("video_path"))
    if video_path and not video_path.startswith(("home/", "mnt/", "tmp/")):
        yield video_path


async def _collect_videos(
    qdrant: AsyncQdrantClient,
    collection: str,
    *,
    only_video_id: str | None,
    page_size: int,
) -> dict[str, LegacyVideo]:
    videos: dict[str, LegacyVideo] = {}
    offset: Any = None
    while True:
        points, offset = await qdrant.scroll(
            collection_name=collection,
            limit=page_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            video_id = str(payload.get("video_id") or "").strip()
            if not video_id or (only_video_id and video_id != only_video_id):
                continue
            item = videos.setdefault(video_id, LegacyVideo(video_id=video_id))
            item.point_ids.append(point.id)
            item.payload_keys.update(_payload_video_keys(payload))
        if offset is None:
            break
    return videos


def _exists(client: Minio, bucket: str, key: str) -> bool:
    try:
        client.stat_object(bucket, key)
        return True
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return False
        raise


def _find_raw_key(client: Minio, bucket: str, video: LegacyVideo) -> str | None:
    candidates = list(video.payload_keys)
    candidates.extend(
        f"videos/{video.video_id}{suffix}" for suffix in (".mp4", ".mov", ".webm", ".mkv")
    )
    seen: set[str] = set()
    for key in candidates:
        if key in seen:
            continue
        seen.add(key)
        if _exists(client, bucket, key):
            return key

    # Last-resort discovery supports unusual but deterministic extensions.
    objects = client.list_objects(bucket, prefix=f"videos/{video.video_id}", recursive=True)
    return next((obj.object_name for obj in objects if obj.object_name), None)


async def migrate(args: argparse.Namespace) -> int:
    settings = get_settings()
    minio_settings = settings.minio
    qdrant = get_qdrant_client()
    client = Minio(
        endpoint=minio_settings.endpoint,
        access_key=minio_settings.access_key.get_secret_value(),
        secret_key=minio_settings.secret_key.get_secret_value(),
        secure=minio_settings.secure,
        region=minio_settings.region,
    )
    raw_bucket = args.raw_bucket or minio_settings.raw_bucket
    derived_bucket = args.derived_bucket or minio_settings.derived_bucket
    collection = args.collection or settings.qdrant.collection
    apply = args.apply and args.confirm_publish_raw

    if args.apply and not args.confirm_publish_raw:
        raise SystemExit("--apply requires --confirm-publish-raw")

    videos = await _collect_videos(
        qdrant,
        collection,
        only_video_id=args.video_id,
        page_size=args.page_size,
    )
    if args.limit is not None:
        videos = dict(list(videos.items())[: args.limit])

    counts: defaultdict[str, int] = defaultdict(int)
    for video in videos.values():
        raw_key = _find_raw_key(client, raw_bucket, video)
        if raw_key is None:
            counts["missing_raw"] += 1
            print(f"MISSING  {video.video_id}: no source object in {raw_bucket}")
            continue

        # Preserve the real extension.  The Qdrant payload removes the media
        # API's legacy `.mov` guess, so MP4 and MOV datasets both work.
        suffix = PurePosixPath(raw_key).suffix.lower()
        derived_key = f"videos/{video.video_id}{suffix or '.mp4'}"
        destination_exists = _exists(client, derived_bucket, derived_key)
        action = "KEEP" if destination_exists else "COPY"
        print(
            f"{action:7} {raw_bucket}/{raw_key} -> {derived_bucket}/{derived_key} "
            f"({len(video.point_ids)} points)"
        )

        if apply:
            if not destination_exists:
                client.copy_object(
                    derived_bucket,
                    derived_key,
                    CopySource(raw_bucket, raw_key),
                )
                counts["copied"] += 1
            else:
                counts["already_derived"] += 1
            await qdrant.set_payload(
                collection_name=collection,
                payload={"minio_video_key": derived_key},
                points=video.point_ids,
                wait=True,
            )
            counts["points_updated"] += len(video.point_ids)
        else:
            counts["planned"] += 1

    mode = "APPLIED" if apply else "DRY-RUN"
    summary = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(f"{mode}: videos_scanned={len(videos)} {summary}".rstrip())
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform copies and Qdrant updates")
    parser.add_argument(
        "--confirm-publish-raw",
        action="store_true",
        help="confirm that selected raw videos are approved for serving",
    )
    parser.add_argument("--video-id", help="migrate one video before running the full collection")
    parser.add_argument("--limit", type=int, help="limit the number of unique videos")
    parser.add_argument("--page-size", type=int, default=256)
    parser.add_argument("--collection")
    parser.add_argument("--raw-bucket")
    parser.add_argument("--derived-bucket")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(migrate(parse_args())))
