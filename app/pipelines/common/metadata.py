"""Metadata validation and explicit unknown enrichment results."""

from __future__ import annotations

from typing import Any, Literal

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
        if set(self.present_concepts) & set(self.absent_concepts):
            raise ValueError("VLM concepts have conflicting polarity")
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
