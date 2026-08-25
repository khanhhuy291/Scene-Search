"""Video-ingestion API endpoints."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from api.deps import require_admin
from infrastructure.minio import get_derived_storage, get_raw_storage
from repositories import corpus
from repositories.task_status import (
    create_task_status,
    get_task_status,
    list_task_statuses,
    update_task_status,
)
from schemas.task import TaskStatus, TaskStatusPage, TaskStatusResponse
from search.index import delete_by_video
from services.embedding_model import require_qwen_embedding_ready
from worker.celery_app import celery_app
from worker.tasks.ingestion import process_video_ingestion

router = APIRouter(tags=["ingestion"], dependencies=[Depends(require_admin)])
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
_ALLOWED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
_PIPELINE_VERSION = "scene-ingestion-v1"

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


@router.post(
    "/ingest/upload", response_model=TaskStatusResponse, status_code=status.HTTP_202_ACCEPTED
)
async def upload_and_create_ingestion_task(
    file: UploadFile = File(...),
    _: None = Depends(require_qwen_embedding_ready),
) -> TaskStatusResponse:
    """Stream an upload to raw MinIO, register it, and enqueue by identifiers."""
    filename = Path(file.filename or "upload.bin").name
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported video format")

    digest = hashlib.sha256()
    size = 0
    claimed = False
    with TemporaryDirectory(prefix="scenesearch-upload-") as directory:
        local_path = Path(directory) / f"upload{suffix}"
        try:
            with local_path.open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > _MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Upload exceeds 500 MB")
                    digest.update(chunk)
                    destination.write(chunk)
        finally:
            await file.close()
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        video_id, created = await corpus.upsert_video(
            checksum=digest.hexdigest(),
            source_uri=f"upload://{filename}",
            dataset="uploads",
            external_id=filename,
        )
        raw_key = f"raw/{video_id}/source{suffix}"
        if created:
            try:
                await asyncio.to_thread(
                    get_raw_storage().upload_file,
                    raw_key,
                    local_path,
                    content_type=file.content_type or "application/octet-stream",
                )
                await corpus.set_video_assets(video_id, raw_object_key=raw_key)
            except Exception as exc:
                await corpus.delete_video(video_id)
                raise HTTPException(
                    status_code=503, detail="Unable to store uploaded video"
                ) from exc
        if not await corpus.is_video_indexed(video_id):
            claimed = await corpus.claim_video_ingestion(video_id)
            if not claimed:
                raise HTTPException(status_code=409, detail="This video is already being processed")

    task_id = str(uuid4())
    try:
        record = await create_task_status(
            task_id,
            filename,
            video_id=str(video_id),
            celery_task_id=task_id,
            pipeline_version=_PIPELINE_VERSION,
        )
    except Exception:
        if claimed:
            await corpus.mark_video_ingestion_failed(video_id)
        raise
    try:
        await asyncio.to_thread(
            process_video_ingestion.apply_async,
            kwargs={"task_id": task_id, "video_id": str(video_id)},
            task_id=task_id,
        )
    except Exception as exc:
        await corpus.mark_video_ingestion_failed(video_id)
        await update_task_status(
            task_id,
            TaskStatus.FAILED,
            progress=0,
            error="Unable to enqueue ingestion task",
            error_code="enqueue_failed",
        )
        raise HTTPException(status_code=503, detail="Unable to enqueue ingestion task") from exc
    return record


@router.get("/tasks", response_model=TaskStatusPage)
async def list_ingestion_tasks(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
) -> TaskStatusPage:
    items, total = await list_task_statuses(limit=limit, offset=offset, status=task_status)
    return TaskStatusPage(items=items, total=total, limit=limit, offset=offset)


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(video_id: UUID) -> None:
    """Cancel active ingestion and remove a video's persisted artifacts."""
    plan = await corpus.prepare_video_deletion(video_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        # Persist cancellation first. A worker reaching its next stage boundary
        # now stops cooperatively even if the revoke broadcast is delayed.
        await corpus.cancel_video_tasks(video_id)
        for celery_task_id in plan.celery_task_ids:
            await asyncio.to_thread(
                celery_app.control.revoke,
                celery_task_id,
                terminate=False,
            )
        await delete_by_video(str(video_id))
        await asyncio.to_thread(get_raw_storage().delete_prefix, f"raw/{video_id}/")
        await asyncio.to_thread(get_derived_storage().delete_prefix, f"videos/{video_id}/")
        await asyncio.to_thread(get_derived_storage().delete_prefix, f"thumbnails/{video_id}/")
        await corpus.delete_video(video_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to completely delete video; retry the request",
        ) from exc


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
