"""Video-ingestion API endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, status
from loguru import logger

from repositories.task_status import create_task_status, get_task_status, update_task_status
from schemas.task import IngestionTaskCreate, TaskStatus, TaskStatusResponse
from worker.celery_app import celery_app
from worker.tasks.ingestion import ingest_video as process_video_ingestion

router = APIRouter(tags=["ingestion"])

_CELERY_STATE_MAP = {
    "PENDING": TaskStatus.PENDING,
    "RECEIVED": TaskStatus.QUEUED,
    "STARTED": TaskStatus.PROCESSING,
    "PROGRESS": TaskStatus.PROCESSING,
    "RETRY": TaskStatus.RETRYING,
    "SUCCESS": TaskStatus.COMPLETED,
    "FAILURE": TaskStatus.FAILED,
    "REVOKED": TaskStatus.FAILED,
}


@router.post("/ingest", response_model=TaskStatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_ingestion_task(request: IngestionTaskCreate) -> TaskStatusResponse:
    task_id = str(uuid4())
    try:
        record = await create_task_status(task_id, request.video_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task status stores are unavailable",
        ) from exc

    try:
        # An explicit Celery id keeps the public API id, custom status-store id,
        # and Celery result-backend id identical. ``apply_async`` is Celery's
        # id-aware equivalent of ``delay``.
        await asyncio.to_thread(
            process_video_ingestion.apply_async,
            args=(task_id, request.video_path),
            task_id=task_id,
        )
    except Exception as exc:
        try:
            await update_task_status(
                task_id,
                TaskStatus.FAILED,
                progress=0,
                error="Unable to enqueue ingestion task",
            )
        except Exception:
            # The enqueue failure remains the primary error reported to the API.
            logger.exception(
                "Unable to persist enqueue failure for task {task_id}", task_id=task_id
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to enqueue ingestion task",
        ) from exc
    return record


def _celery_fallback(task_id: str) -> TaskStatusResponse | None:
    result = AsyncResult(task_id, app=celery_app)
    if result.state == "PENDING":
        return None
    info = result.info if isinstance(result.info, dict) else {}
    payload = result.result if result.successful() and isinstance(result.result, dict) else None
    try:
        progress = int(info.get("progress", 100 if result.successful() else 0))
    except (TypeError, ValueError):
        progress = 0
    return TaskStatusResponse(
        task_id=task_id,
        status=_CELERY_STATE_MAP.get(result.state, TaskStatus.PENDING),
        progress=max(0, min(100, progress)),
        result=payload,
        error=str(result.result) if result.failed() else None,
        updated_at=datetime.now(UTC),
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def read_ingestion_task(task_id: UUID) -> TaskStatusResponse:
    task_id_string = str(task_id)
    try:
        record = await get_task_status(task_id_string)
        if record is not None:
            return record
        celery_record = await asyncio.to_thread(_celery_fallback, task_id_string)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task status backends are unavailable",
        ) from exc
    if celery_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return celery_record


__all__ = ["router"]
