"""Retry-safe Qdrant scene indexing contract."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any, Protocol

from pipelines.common.errors import PersistenceError, RetryablePersistenceError
from pipelines.common.types import EmbeddingRecord, SceneRecord
from search.points import ScenePayload, build_point


def build_scene_points(
    scenes: Sequence[SceneRecord], embeddings: Sequence[EmbeddingRecord], *, dataset: str
) -> list[object]:
    by_id = {embedding.scene_id: embedding for embedding in embeddings}
    points: list[object] = []
    for scene in scenes:
        embedding = by_id.get(scene.scene_id)
        if embedding is None:
            raise PersistenceError(
                f"Missing embedding for scene {scene.scene_id}", stage="persistence"
            )
        objects = sorted({d.class_name for f in scene.keyframes for d in f.detections})
        object_counts: dict[str, int] = {}
        for frame in scene.keyframes:
            per_frame = Counter(detection.class_name for detection in frame.detections)
            for class_name, count in per_frame.items():
                object_counts[class_name] = max(object_counts.get(class_name, 0), count)
        behaviors = sorted({behavior.kind for behavior in scene.behaviors})
        payload = ScenePayload(
            frame_id=None,
            segment_id=scene.scene_id,
            video_id=scene.video_id,
            dataset=dataset,
            granularity="segment",
            ts_start_s=scene.start_ms / 1000,
            ts_end_s=scene.end_ms / 1000,
            model_version=embedding.version,
            objects=objects,
            object_counts=object_counts,
            behaviors=behaviors,
        )
        data = payload.to_dict()
        data.update(
            scene_id=scene.scene_id,
            start_ms=scene.start_ms,
            end_ms=scene.end_ms,
            privacy_status=scene.privacy_status,
            embedding_model=embedding.model,
            embedding_version=embedding.version,
            thumbnail_key=scene.thumbnail_key,
            video_key=scene.preview_key,
        )
        point = build_point("segment", scene.scene_id, embedding.vector, payload)
        point.payload = data
        points.append(point)
    return points


class _SceneIndexer(Protocol):
    async def reindex_video(self, video_id: str, points: Sequence[Any]) -> int: ...


async def persist_vectors(
    video_id: str, points: Sequence[object], scene_indexer: _SceneIndexer
) -> int:
    try:
        return await scene_indexer.reindex_video(video_id, points)
    except ValueError as exc:
        raise PersistenceError("Invalid Qdrant vector configuration", stage="persistence") from exc
    except Exception as exc:
        raise RetryablePersistenceError(
            "Unable to persist Qdrant scene vectors", stage="persistence"
        ) from exc


__all__ = ["build_scene_points", "persist_vectors"]
