"""Typed values passed between ingestion stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from PIL.Image import Image

PrivacyStatus = Literal["pending", "verified", "failed"]


@dataclass(frozen=True)
class DetectionRecord:
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]
    source: str
    track_id: str | None = None


@dataclass(frozen=True)
class BehaviorRecord:
    kind: str
    start_ms: int
    end_ms: int
    confidence: float
    source: str
    track_id: str | None = None


@dataclass
class FrameRecord:
    timestamp_ms: int
    frame_index: int
    image: Image
    metadata: dict[str, Any] = field(default_factory=dict)
    detections: list[DetectionRecord] = field(default_factory=list)
    behaviors: list[BehaviorRecord] = field(default_factory=list)
    privacy_status: PrivacyStatus = "pending"
    privacy_region_count: int = 0
    covers_start_ms: int | None = None
    covers_end_ms: int | None = None
    embedding: list[float] | None = None


@dataclass
class SceneRecord:
    scene_id: str
    video_id: str
    start_ms: int
    end_ms: int
    keyframes: list[FrameRecord]
    metadata: dict[str, Any] = field(default_factory=dict)
    behaviors: list[BehaviorRecord] = field(default_factory=list)
    thumbnail_key: str | None = None
    preview_key: str | None = None
    privacy_status: PrivacyStatus = "pending"


@dataclass(frozen=True)
class EmbeddingRecord:
    scene_id: str
    vector: list[float]
    model: str
    version: str


__all__ = [
    "BehaviorRecord",
    "DetectionRecord",
    "EmbeddingRecord",
    "FrameRecord",
    "PrivacyStatus",
    "SceneRecord",
]
