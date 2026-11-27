"""Metadata validation and explicit unknown enrichment results."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SceneAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_type: Literal[
        "residential", "urban", "highway", "rural", "tunnel", "parking", "unknown"
    ] = "unknown"
    road_type: Literal["residential", "city_street", "highway", "country_road", "unknown"] = (
        "unknown"
    )
    weather: Literal["clear", "rainy", "foggy", "overcast", "snowy", "unknown"] = "unknown"
    time_of_day: Literal["day", "night", "dusk", "dawn", "unknown"] = "unknown"
    lighting: Literal["daylight", "artificial", "dim", "dark", "unknown"] = "unknown"
    road_surface: Literal["dry", "wet", "snowy", "muddy", "unknown"] = "unknown"
    visibility: Literal["high", "good", "medium", "low", "unknown"] = "unknown"
    traffic_density: Literal["empty", "low", "medium", "heavy", "unknown"] = "unknown"


class TrafficLight(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    present: bool | None = None
    state: Literal["unknown", "red", "green", "yellow"] = "unknown"

    @model_validator(mode="after")
    def validate_state(self) -> TrafficLight:
        if self.present is False and self.state != "unknown":
            raise ValueError("Absent traffic light cannot have an observed state")
        return self


class TrafficControl(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    traffic_light: TrafficLight = Field(default_factory=TrafficLight)
    signs: list[str] = Field(default_factory=list)


class RoadAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    lane_count: int | None = Field(default=None, ge=1)
    ego_lane: Literal["unknown", "left", "center", "right"] = "unknown"
    lane_marking: Literal["none", "solid", "dashed", "unknown"] = "unknown"
    intersection: bool | None = None
    roundabout: bool | None = None
    curve: Literal["straight", "left", "right", "unknown"] = "unknown"
    road_markings: list[str] = Field(default_factory=list)


class VLMMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: SceneAttributes = Field(default_factory=SceneAttributes)
    traffic: dict[str, Literal["none", "low", "medium", "high", "unknown"]] = Field(
        default_factory=dict
    )
    traffic_control: TrafficControl = Field(default_factory=TrafficControl)
    road: RoadAttributes = Field(default_factory=RoadAttributes)
    ocr: list[Any] = Field(default_factory=list)
    retrieval_tags: list[str] = Field(default_factory=list)
    caption: str


class VLMResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: VLMMetadata
    present_concepts: list[str] = Field(default_factory=list)
    absent_concepts: list[str] = Field(default_factory=list)
    unknown_concepts: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    object_counts: dict[str, Annotated[int, Field(gt=0, strict=True)] | None] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_evidence(self) -> VLMResult:
        if not self.metadata.caption.strip():
            raise ValueError("VLM caption is empty")
        self.present_concepts = sorted(
            {c.strip().lower() for c in self.present_concepts if c.strip()}
        )
        self.absent_concepts = sorted(
            {c.strip().lower() for c in self.absent_concepts if c.strip()}
        )
        self.unknown_concepts = sorted(
            {c.strip().lower() for c in self.unknown_concepts if c.strip()}
        )
        self.objects = sorted({name.strip().lower() for name in self.objects if name.strip()})
        self.object_counts = {
            name.strip().lower(): count for name, count in self.object_counts.items()
        }
        if not set(self.object_counts) <= set(self.objects):
            raise ValueError("VLM object counts must refer to observed objects")
        positive = set(self.present_concepts) | set(self.objects)
        if positive & set(self.absent_concepts):
            raise ValueError("VLM concepts have conflicting polarity")
        if set(self.unknown_concepts) & (positive | set(self.absent_concepts)):
            raise ValueError("Unknown VLM concepts cannot also be present or absent")
        return self


class VLMFrameObservation(VLMResult):
    frame_index: int = Field(ge=0, strict=True)
    timestamp_ms: int = Field(ge=0, strict=True)
    objects: list[str] = Field(...)


class TemporalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    frame_indices: list[Annotated[int, Field(ge=0, strict=True)]] = Field(min_length=2)
    timestamps_ms: list[Annotated[int, Field(ge=0, strict=True)]] = Field(min_length=2)
    source: Literal["vlm_inference"] = "vlm_inference"

    @model_validator(mode="after")
    def validate_references(self) -> TemporalObservation:
        if not self.description.strip():
            raise ValueError("Temporal observation description is empty")
        if len(self.frame_indices) != len(self.timestamps_ms) or len(
            set(self.frame_indices)
        ) != len(self.frame_indices):
            raise ValueError("Temporal observations require distinct matching references")
        if any(right <= left for left, right in zip(self.timestamps_ms, self.timestamps_ms[1:])):
            raise ValueError("Temporal observations must be chronological")
        return self


class VLMSequenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: str = Field(min_length=1)
    observations: list[VLMFrameObservation] = Field(min_length=1)
    temporal_observations: list[TemporalObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sequence(self) -> VLMSequenceResult:
        if not self.caption.strip():
            raise ValueError("VLM sequence caption is empty")
        references = {
            observation.frame_index: observation.timestamp_ms for observation in self.observations
        }
        if len(references) != len(self.observations):
            raise ValueError("Duplicate VLM observation frame index")
        for observation in self.temporal_observations:
            if any(
                references.get(index) != timestamp
                for index, timestamp in zip(
                    observation.frame_indices, observation.timestamps_ms, strict=True
                )
            ):
                raise ValueError("Temporal observation lacks matching frame evidence")
        return self


def unknown_metadata(
    objects: list[str], *, status: str, reason: str, timestamp_ms: int
) -> dict[str, Any]:
    """Only supplied detector observations are positive evidence; silence is unknown."""
    return {
        "metadata": {
            "scene": SceneAttributes().model_dump(),
            "traffic": {},
            "traffic_control": {},
            "road": {},
            "ocr": [],
            "retrieval_tags": sorted(set(objects)),
            "caption": "",
        },
        "present_concepts": sorted(set(objects)),
        "absent_concepts": [],
        "enrichment": {
            "status": status,
            "source": "fallback",
            "reason": reason,
            "timestamp_ms": timestamp_ms,
        },
    }
