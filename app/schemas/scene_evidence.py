"""Persisted scene evidence shared by ingestion and search adapters."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelines.common.metadata import TemporalObservation


class SceneObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    source: str
    status: Literal["success", "failed", "not_configured"]
    model: str | None = None
    prompt_version: str | None = None
    reason: str | None = None
    caption: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    present_concepts: list[str] = Field(default_factory=list)
    absent_concepts: list[str] = Field(default_factory=list)
    unknown_concepts: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    object_counts: dict[str, int] = Field(default_factory=dict)
    behaviors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_evidence(self) -> "SceneObservation":
        if set(self.present_concepts) & set(self.absent_concepts):
            raise ValueError("Observation has contradictory concepts")
        if set(self.unknown_concepts) & (set(self.present_concepts) | set(self.absent_concepts)):
            raise ValueError("Observation has contradictory unknown concepts")
        if any(count < 1 for count in self.object_counts.values()):
            raise ValueError("Observed object counts must be positive")
        return self


class SceneEvidence(BaseModel):
    # Summary metadata (caption, scene, road, etc.) remains in the same JSON object.
    model_config = ConfigDict(extra="allow")

    observations: list[SceneObservation]
    sampled_count: int | None = Field(default=None, ge=1)
    candidate_count: int = Field(ge=1)
    succeeded_count: int = Field(ge=0)
    temporal_observations: list[TemporalObservation] = Field(default_factory=list)
    complete_for_selected_frames: bool
    coverage_scope: Literal["selected_instants"] = "selected_instants"
    observed_timestamps_ms: list[int]
    representative_frame_index: int = Field(ge=0)
    representative_timestamp_ms: int = Field(ge=0)
    present_concepts: list[str]
    absent_concepts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_selection(self) -> "SceneEvidence":
        successful = {
            o.frame_index: o.timestamp_ms for o in self.observations if o.status == "success"
        }
        for observation in self.temporal_observations:
            if any(
                successful.get(index) != timestamp
                for index, timestamp in zip(
                    observation.frame_indices, observation.timestamps_ms, strict=True
                )
            ):
                raise ValueError("Temporal inference requires successful observation evidence")
        if len(self.observations) != self.candidate_count:
            raise ValueError("Observation count does not match selection")
        if len({o.frame_index for o in self.observations}) != self.candidate_count:
            raise ValueError("Scene observations must have distinct frame indices")
        if not any(
            o.frame_index == self.representative_frame_index
            and o.timestamp_ms == self.representative_timestamp_ms
            for o in self.observations
        ):
            raise ValueError("Representative reference must match an observation")
        if self.sampled_count is not None and self.sampled_count < self.candidate_count:
            raise ValueError("Selection exceeds sampled frame count")
        succeeded = sum(o.status == "success" for o in self.observations)
        if self.succeeded_count != succeeded:
            raise ValueError("Invalid enrichment success count")
        if self.complete_for_selected_frames != (succeeded == self.candidate_count):
            raise ValueError("Invalid selected-frame completion status")
        if self.absent_concepts:
            raise ValueError("Sparse observations cannot assert scene-level absence")
        if set(self.present_concepts) != {c for o in self.observations for c in o.present_concepts}:
            raise ValueError("Scene positives must match observation evidence")
        if sorted(set(self.observed_timestamps_ms)) != sorted(
            {o.timestamp_ms for o in self.observations if o.status == "success"}
        ):
            raise ValueError("Invalid observed timestamp coverage")
        return self
