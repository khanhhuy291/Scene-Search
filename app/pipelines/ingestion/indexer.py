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

        # Extract rich VLM metadata if generated during ingestion
        primary_frame = scene.keyframes[0] if scene.keyframes else None
        vlm_data = (primary_frame.metadata.get("vlm_data") if primary_frame else None) or {}
        extracted_meta = vlm_data.get("metadata") or {
            "scene": {
                "scene_type": "residential",
                "road_type": "residential",
                "weather": "clear",
                "time_of_day": "day",
                "lighting": "daylight",
                "road_surface": "dry",
                "visibility": "good",
                "traffic_density": "low",
            },
            "traffic": {
                "cars": "low" if "car" in objects else "none",
                "motorcycles": "none",
                "trucks": "none",
                "buses": "none",
                "pedestrians": "low" if "person" in objects else "none",
            },
            "traffic_control": {
                "traffic_light": {"present": False, "state": "unknown"},
                "signs": [],
            },
            "road": {
                "lane_count": None,
                "ego_lane": "unknown",
                "lane_marking": "none",
                "intersection": False,
                "roundabout": False,
                "curve": "straight",
                "road_markings": [],
            },
            "ocr": [],
            "retrieval_tags": sorted(set(objects + behaviors + ["driving", "dashcam"])),
            "caption": f"Dashcam driving scene at {scene.start_ms / 1000.0:.1f}s.",
        }
        present_concepts = vlm_data.get("present_concepts") or objects or ["car", "road"]
        absent_concepts = vlm_data.get("absent_concepts") or ["night", "rain"]

        frame_index = getattr(primary_frame, "frame_index", 0) if primary_frame else 0
        minio_path = scene.thumbnail_key or f"{scene.video_id}/frame_{frame_index:05d}.jpg"

        data.update(
            frame_id=frame_index,
            frame_name=f"frame_{frame_index:05d}.jpg",
            minio_path=minio_path,
            metadata=extracted_meta,
            video_second=round(scene.start_ms / 1000.0, 2),
            present_concepts=present_concepts,
            absent_concepts=absent_concepts,
            scene_id=scene.scene_id,
            start_ms=scene.start_ms,
            end_ms=scene.end_ms,
            privacy_status=scene.privacy_status,
            embedding_model=embedding.model,
            embedding_version=embedding.version,
            thumbnail_key=scene.thumbnail_key,
            video_key=scene.preview_key,
            playback_timeline="source",
            playback_anonymized=False,
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
        from loguru import logger

        logger.exception(
            "Failed to persist Qdrant scene vectors for video {video_id}: {exc}",
            video_id=video_id,
            exc=exc,
        )
        raise RetryablePersistenceError(
            f"Unable to persist Qdrant scene vectors: {exc}", stage="persistence"
        ) from exc


__all__ = ["build_scene_points", "persist_vectors"]
