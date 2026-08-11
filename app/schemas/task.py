"""Contracts shared by ingestion endpoints and task-status storage."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class IngestionTaskCreate(BaseModel):
    """Request to ingest a local video path or an HTTP(S) video URL."""

    model_config = ConfigDict(str_strip_whitespace=True)

    video_path: str = Field(min_length=1, max_length=4096)

    @field_validator("video_path")
    @classmethod
    def validate_video_location(cls, value: str) -> str:
        if value.startswith(("http://", "https://")):
            return value
        if "://" in value:
            raise ValueError("video_path must be a local path or an HTTP(S) URL")
        return value


class TaskStatusResponse(BaseModel):
    """Serializable ingestion-task state returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    task_id: str
    status: TaskStatus
    video_path: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = ["IngestionTaskCreate", "TaskStatus", "TaskStatusResponse"]
