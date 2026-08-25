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
    CANCELLED = "cancelled"


class TaskStatusResponse(BaseModel):
    """Serializable ingestion-task state returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    task_id: str
    status: TaskStatus
    video_path: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    result: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    video_id: str | None = None
    celery_task_id: str | None = None
    pipeline_version: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("task_id", "video_id", mode="before")
    @classmethod
    def stringify_uuid(cls, value: Any) -> Any:
        return str(value) if value is not None else value


class TaskStatusPage(BaseModel):
    items: list[TaskStatusResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


__all__ = ["TaskStatus", "TaskStatusPage", "TaskStatusResponse"]
