"""Contracts for live admin telemetry and eval reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LabelCount(BaseModel):
    name: str
    count: int


class CorpusHealth(BaseModel):
    videos: int = 0
    keyframes: int = 0
    media_coverage_pct: int = 0
    caption_coverage_pct: int = 0
    embedding_coverage_pct: int = 0
    caption_tower_installed: bool = False
    caption_tower_name: str = ""
    labels: dict[str, list[LabelCount]] = Field(default_factory=dict)


class VectorSummary(BaseModel):
    name: str
    size: int | None = None
    distance: str = ""


class QdrantHealth(BaseModel):
    reachable: bool = False
    collection: str = ""
    points_count: int | None = None
    vectors: list[VectorSummary] = Field(default_factory=list)
    hnsw_m: int | None = None
    ef_construct: int | None = None
    detail: str | None = None


class BucketUsage(BaseModel):
    name: str
    objects: int | None = None
    bytes: int | None = None
    detail: str | None = None


class StorageHealth(BaseModel):
    reachable: bool = False
    buckets: list[BucketUsage] = Field(default_factory=list)
    detail: str | None = None


class WorkerNode(BaseModel):
    id: str
    status: str
    concurrency_max: int | None = None
    active_count: int = 0
    reserved_count: int = 0
    active_tasks: list[str] = Field(default_factory=list)
    processed: int | None = None


class WorkerHealth(BaseModel):
    reachable: bool = False
    broker: str = ""
    worker_count: int = 0
    queue_depth: int | None = None
    workers: list[WorkerNode] = Field(default_factory=list)
    detail: str | None = None


class RecentJob(BaseModel):
    task_id: str
    video_path: str
    status: str
    progress: int = 0
    updated_at: str | None = None
    error: str | None = None


class AdminTelemetry(BaseModel):
    generated_at: str
    corpus: CorpusHealth
    qdrant: QdrantHealth
    storage: StorageHealth
    workers: WorkerHealth
    recent_jobs: list[RecentJob] = Field(default_factory=list)
    job_total: int = 0


class EvalReportResponse(BaseModel):
    available: bool
    path: str | None = None
    generated_at: str | None = None
    report: dict[str, Any] | None = None
    detail: str | None = None


class EmbeddingModelStatus(BaseModel):
    state: Literal["unloaded", "loading", "ready", "busy", "unloading", "error"]
    model: str
    dimension: int
    error: str | None = None
    gpu_memory_allocated_mb: float | None = None
    gpu_memory_reserved_mb: float | None = None
