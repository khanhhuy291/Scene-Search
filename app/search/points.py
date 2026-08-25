"""Qdrant point payloads and filter construction.

Payloads are denormalized from Postgres so that metadata filters are evaluated
*inside* Qdrant. This is not a micro-optimization: filtering after the ANN search
returns whatever survives from a fixed candidate set, so a narrow filter would
yield very few results. Prefiltering instead prunes the HNSW traversal, and a
narrower filter makes the search both faster and more complete.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# Namespace for deriving stable point ids. Qdrant requires a UUID or an integer,
# while the pipeline works with (kind, database id) pairs; deriving the id makes
# re-indexing idempotent, since the same frame always maps to the same point.
POINT_NAMESPACE = uuid.UUID("6f1d4b6e-7c1a-4f7f-9a2e-1b0c5d3e8a41")

Granularity = Literal["frame", "segment"]


def point_id(granularity: Granularity, entity_id: str) -> str:
    """Derive a deterministic point id from an entity id."""

    return str(uuid.uuid5(POINT_NAMESPACE, f"{granularity}:{entity_id}"))


@dataclass
class ScenePayload:
    """The filterable facts stored alongside a vector."""

    frame_id: str | None
    segment_id: str | None
    video_id: str
    dataset: str
    granularity: Granularity
    ts_start_s: float
    ts_end_s: float
    model_version: str
    split: str | None = None
    weather: str | None = None
    timeofday: str | None = None
    scene: str | None = None
    objects: list[str] = field(default_factory=list)
    object_counts: dict[str, int] = field(default_factory=dict)
    behaviors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "video_id": self.video_id,
            "dataset": self.dataset,
            "granularity": self.granularity,
            "ts_start_s": self.ts_start_s,
            "ts_end_s": self.ts_end_s,
            "model_version": self.model_version,
            "objects": sorted(self.objects),
            "object_counts": self.object_counts,
            "behaviors": sorted(self.behaviors),
        }
        # Omit rather than store nulls: Qdrant's IsNull matching is separate from
        # value matching, and absent keys keep the payload index smaller.
        optional = {
            "frame_id": self.frame_id,
            "segment_id": self.segment_id,
            "split": self.split,
            "weather": self.weather,
            "timeofday": self.timeofday,
            "scene": self.scene,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        return payload


def build_filter(
    *,
    dataset: list[str] | None = None,
    split: list[str] | None = None,
    video_ids: list[str] | None = None,
    weather: list[str] | None = None,
    timeofday: list[str] | None = None,
    scene: list[str] | None = None,
    objects_any: list[str] | None = None,
    objects_all: list[str] | None = None,
    behaviors: list[str] | None = None,
    granularity: Granularity | None = None,
    model_version: str | None = None,
    time_range_s: tuple[float, float] | None = None,
) -> Any | None:
    """Build a Qdrant filter, or ``None`` when nothing is constrained.

    ``objects_any`` becomes one match-any condition; ``objects_all`` becomes one
    condition per class, since Qdrant's keyword match on an array is
    "contains any" and conjunction has to be expressed as separate musts.
    """

    from qdrant_client.http import models

    must: list[Any] = []
    must_not: list[Any] = []

    def any_of(key: str, values: list[str] | None) -> None:
        if values:
            must.append(models.FieldCondition(key=key, match=models.MatchAny(any=list(values))))

    any_of("dataset", dataset)
    any_of("split", split)
    any_of("video_id", video_ids)
    any_of("weather", weather)
    any_of("timeofday", timeofday)
    any_of("scene", scene)
    any_of("objects", objects_any)
    any_of("behaviors", behaviors)

    for class_name in objects_all or []:
        must.append(models.FieldCondition(key="objects", match=models.MatchValue(value=class_name)))

    if granularity == "segment":
        must.append(
            models.FieldCondition(key="granularity", match=models.MatchValue(value="segment"))
        )
    elif granularity == "frame":
        must_not.append(
            models.FieldCondition(key="granularity", match=models.MatchValue(value="segment"))
        )
    if model_version:
        must.append(
            models.FieldCondition(key="model_version", match=models.MatchValue(value=model_version))
        )
    if time_range_s:
        start, end = time_range_s
        if start > end:
            raise ValueError(f"time_range_s start {start} is after end {end}")
        # Overlap, not containment: a segment spanning the requested window
        # should match even if it starts before or ends after it.
        must.append(models.FieldCondition(key="ts_end_s", range=models.Range(gte=start)))
        must.append(models.FieldCondition(key="ts_start_s", range=models.Range(lte=end)))

    if must or must_not:
        return models.Filter(must=must or None, must_not=must_not or None)
    return None


def build_point(
    granularity: Granularity,
    entity_id: str,
    vector: list[float],
    payload: ScenePayload,
) -> Any:
    from qdrant_client.http import models

    return models.PointStruct(
        id=point_id(granularity, entity_id),
        vector=vector,
        payload=payload.to_dict(),
    )


__all__ = [
    "Granularity",
    "POINT_NAMESPACE",
    "ScenePayload",
    "build_filter",
    "build_point",
    "point_id",
]
