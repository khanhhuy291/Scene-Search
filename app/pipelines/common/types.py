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
    qwen_embedding: list[float] | None = None
    display_image: Image | None = None

    def close(self) -> None:
        self.image.close()
        if self.display_image is not None and self.display_image is not self.image:
            self.display_image.close()


@dataclass
class SemanticScene:
    scene_id: str
    video_id: str
    start_ms: int
    end_ms: int
    frames: tuple[FrameRecord, ...]
    boundary_reason: str
    boundary_score: float | None = None


@dataclass(frozen=True)
class SceneBoundary:
    frame_offset: int
    score: float
    raw_score: float | None = None
    threshold: float | None = None


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
    siglip_sum: list[float] | None = None
    representative_frame: FrameRecord | None = None
    vlm_candidates: list[FrameRecord] = field(default_factory=list)


@dataclass(frozen=True)
class EmbeddingRecord:
    scene_id: str
    vector: list[float] | dict[str, list[float]]
    model: str
    version: str


@dataclass
class IndexedKeyframe:
    keyframe_id: str
    video_id: str
    semantic_scene_id: str
    frame_index: int
    timestamp_ms: int
    embedding: list[float]
    thumbnail_key: str
    chunk_ids: list[str] = field(default_factory=list)


__all__ = [
    "IndexedKeyframe",
    "BehaviorRecord",
    "DetectionRecord",
    "EmbeddingRecord",
    "FrameRecord",
    "PrivacyStatus",
    "SceneRecord",
    "SceneBoundary",
    "SemanticScene",
]
