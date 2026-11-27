"""Read only publications selected by PostgreSQL, including during re-ingestion."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qdrant_client import models

from core.config import get_settings
from repositories.scene_graph import active_publications
from search.catalog import DEFAULT_TTL_SECONDS, Keyframe, keyframe_from_payload
from search.cursor import fingerprint
from services.catalog_generation import catalog_revision


@dataclass(frozen=True)
class PublishedSnapshot:
    points: dict[str, Any]
    frames: dict[str, Keyframe]
    identity: str


class PublishedChunkCatalog:
    """Cache immutable payload snapshots; active-run changes bypass the TTL."""

    def __init__(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._key = None
        self._snapshot = None
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._key = None
        self._loaded_at = 0.0

    async def load(self, client: Any, publications: dict[str, str]) -> PublishedSnapshot:
        revision = await catalog_revision() if publications else None
        key = (
            get_settings().qdrant.chunk_collection,
            tuple(sorted(publications.items())),
            revision,
        )
        async with self._lock:
            if (
                self._snapshot is not None
                and self._key == key
                and time.monotonic() - self._loaded_at < self.ttl_seconds
            ):
                return self._snapshot
            points = await published_chunks(client, publications)
            frames = {}
            for identifier, point in points.items():
                frame = keyframe_from_payload(identifier, point.payload or {})
                if frame is not None:
                    frames[identifier] = frame
            snapshot = PublishedSnapshot(
                points,
                frames,
                fingerprint(
                    "published-chunks",
                    {identifier: point.payload for identifier, point in sorted(points.items())},
                ),
            )
            self._snapshot, self._key, self._loaded_at = snapshot, key, time.monotonic()
            return snapshot


def publication_filter(publications: dict[str, str]) -> models.Filter:
    if not publications:
        raise ValueError("A publication filter requires at least one active run")
    return models.Filter(
        should=[
            models.Filter(
                must=[
                    models.FieldCondition(key="video_id", match=models.MatchValue(value=video)),
                    models.FieldCondition(
                        key="ingestion_run_id", match=models.MatchValue(value=run)
                    ),
                ]
            )
            for video, run in sorted(publications.items())
        ]
    )


async def published_chunks(client: Any, publications: dict[str, str]) -> dict[str, Any]:
    if not publications:
        return {}
    collection = get_settings().qdrant.chunk_collection
    if not await client.collection_exists(collection):
        raise RuntimeError("The active chunk collection is unavailable")
    points, offset = {}, None
    while True:
        batch, offset = await client.scroll(
            collection_name=collection,
            scroll_filter=publication_filter(publications),
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.update((str(point.id), point) for point in batch)
        if offset is None:
            return points


async def published_point(client: Any, point_id: str) -> Any | None:
    """Media lookups must not expose a staged or superseded point."""
    try:
        UUID(point_id)
    except ValueError:
        return None
    for collection in (
        get_settings().qdrant.chunk_collection,
        get_settings().qdrant.keyframe_collection,
    ):
        if not await client.collection_exists(collection):
            continue
        records = await client.retrieve(
            collection_name=collection, ids=[point_id], with_payload=True
        )
        if records:
            point = records[0]
            data = point.payload or {}
            active = await active_publications({data["video_id"]})
            return point if active.get(data["video_id"]) == data.get("ingestion_run_id") else None
    return None
