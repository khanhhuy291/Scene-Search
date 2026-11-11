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
from pydantic import BaseModel

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


class PresignedUploadRequest(BaseModel):
    filename: str
    content_type: str | None = None


class PresignedUploadResponse(BaseModel):
    upload_url: str
    video_id: str
    raw_key: str


class ProcessUploadRequest(BaseModel):
    video_id: str
    raw_key: str
    filename: str


@router.post(
    "/ingest/presigned-url",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_presigned_upload_url(
    payload: PresignedUploadRequest,
    _: None = Depends(require_qwen_embedding_ready),
) -> PresignedUploadResponse:
    """Generate a temporary direct PUT upload URL for Cloud Storage (bypasses Cloud Run 32MB limit)."""
    filename = Path(payload.filename or "upload.bin").name
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported video format")

    video_id = uuid4()
    raw_key = f"{video_id}{suffix}"

    try:
        raw_storage = get_raw_storage()
        upload_url = raw_storage.get_presigned_upload_url(raw_key)
        return PresignedUploadResponse(
            upload_url=upload_url,
            video_id=str(video_id),
            raw_key=raw_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to generate upload URL: {exc}",
        ) from exc


@router.post(
    "/ingest/process",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_direct_uploaded_video(
    payload: ProcessUploadRequest,
    _: None = Depends(require_qwen_embedding_ready),
) -> TaskStatusResponse:
    """Enqueue Celery ingestion for a video directly uploaded to object storage.

    Mirrors ``/ingest/upload``: claim the video as ``processing`` before enqueue so
    ``mark_video_indexed`` can complete at the end of the worker pipeline.
    """
    try:
        UUID(payload.video_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid video_id UUID")

    # Upsert video record in database
    video_id, _ = await corpus.upsert_video(
        checksum=payload.raw_key,
        source_uri=f"upload://{payload.filename}",
        dataset="uploads",
        external_id=payload.filename,
    )
    await corpus.set_video_assets(video_id, raw_object_key=payload.raw_key)

    claimed = await corpus.claim_video_ingestion(video_id, allow_retry=True)
    if not claimed:
        raise HTTPException(status_code=409, detail="This video is already being processed")

    task_id = str(uuid4())
    try:
        record = await create_task_status(
            task_id,
            payload.filename,
            video_id=str(video_id),
            celery_task_id=task_id,
            pipeline_version=_PIPELINE_VERSION,
        )
    except Exception:
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
        raw_key = f"{video_id}{suffix}"
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
        else:
            # Video already in MinIO: if already fully indexed, return completed duplicate record
            if await corpus.is_video_indexed(video_id):
                task_id = str(uuid4())
                record = await create_task_status(
                    task_id,
                    filename,
                    video_id=str(video_id),
                    celery_task_id=task_id,
                    pipeline_version=_PIPELINE_VERSION,
                )
                await update_task_status(
                    task_id,
                    TaskStatus.COMPLETED,
                    progress=100,
                    result={"video_id": str(video_id), "duplicate": True, "scenes_indexed": 0},
                )
                return record

            # Video in database but previous run failed or was incomplete -> upload file and update raw_object_key
            try:
                await asyncio.to_thread(
                    get_raw_storage().upload_file,
                    raw_key,
                    local_path,
                    content_type=file.content_type or "application/octet-stream",
                )
                await corpus.set_video_assets(video_id, raw_object_key=raw_key)
            except Exception as exc:
                raise HTTPException(
                    status_code=503, detail="Unable to store uploaded video in storage"
                ) from exc

        claimed = await corpus.claim_video_ingestion(video_id, allow_retry=True)
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


@router.post(
    "/ingest/reprocess/{video_id}",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_existing_video(
    video_id: UUID,
    force: bool = Query(default=False, description="Force re-indexing even if already indexed"),
    _: None = Depends(require_qwen_embedding_ready),
) -> TaskStatusResponse:
    """Reprocess an existing video already stored in MinIO/GCS (e.g. after failure or re-indexing)."""
    video = await corpus.get_video_for_pipeline(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.raw_object_key:
        raise HTTPException(status_code=400, detail="Video has no raw storage object in MinIO")

    if not force and await corpus.is_video_indexed(video_id):
        task_id = str(uuid4())
        record = await create_task_status(
            task_id,
            video.external_id or f"video_{video_id}",
            video_id=str(video_id),
            celery_task_id=task_id,
            pipeline_version=_PIPELINE_VERSION,
        )
        await update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100,
            result={"video_id": str(video_id), "duplicate": True, "scenes_indexed": 0},
        )
        return record

    claimed = await corpus.claim_video_ingestion(video_id, allow_retry=True)
    if not claimed:
        raise HTTPException(status_code=409, detail="This video is already being processed")

    task_id = str(uuid4())
    try:
        record = await create_task_status(
            task_id,
            video.external_id or f"video_{video_id}",
            video_id=str(video_id),
            celery_task_id=task_id,
            pipeline_version=_PIPELINE_VERSION,
        )
    except Exception:
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
        if plan.raw_object_key:
            await asyncio.to_thread(get_raw_storage().delete_object, plan.raw_object_key)
        await asyncio.to_thread(get_raw_storage().delete_prefix, f"raw/{video_id}/")
        await asyncio.to_thread(get_derived_storage().delete_prefix, f"videos/{video_id}/")
        await asyncio.to_thread(get_derived_storage().delete_prefix, f"thumbnails/{video_id}/")
        # Legacy ingestion stored thumbnails and the overwritten preview here.
        await asyncio.to_thread(get_derived_storage().delete_prefix, f"{video_id}/")
        await asyncio.to_thread(get_derived_storage().delete_object, f"{video_id}.mp4")
        await corpus.delete_video(video_id)
        from api.v1.media import reset_media_client
        from search.catalog import reset_catalog

        reset_media_client()
        reset_catalog()
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
