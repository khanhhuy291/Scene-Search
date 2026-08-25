"""Contracts for exporting an engineer-selected dataset as a zip."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatasetExportItem(BaseModel):
    point_id: str = Field(min_length=1, max_length=128)
    video_id: str | None = None
    ts_start_s: float | None = None
    ts_end_s: float | None = None
    caption: str | None = None
    query: str | None = None
    required_concepts: list[str] = Field(default_factory=list)
    excluded_concepts: list[str] = Field(default_factory=list)
    weather: str | None = None
    time_of_day: str | None = None
    objects: list[str] = Field(default_factory=list)


class DatasetExportRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="dataset", max_length=255)
    queries: list[str] = Field(default_factory=list)
    model_version: str | None = None
    items: list[DatasetExportItem] = Field(min_length=1, max_length=200)
