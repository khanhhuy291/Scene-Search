"""Admin telemetry and eval-report endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import require_admin
from db.models.review import User
from schemas.admin import AdminTelemetry, EmbeddingModelStatus, EvalReportResponse
from services.admin import collect_telemetry, load_eval_report
from services.embedding_model import embedding_model_request
from repositories.task_status import create_task_status, update_task_status
from schemas.task import TaskStatus, TaskStatusResponse
from worker.tasks.caption_refresh import refresh_fallback_captions

router = APIRouter(prefix="/admin", tags=["admin"])


class CaptionRefreshRequest(BaseModel):
    """Optional video scope; omitted or empty refreshes all fallback captions."""

    video_ids: list[UUID] | None = Field(default=None, max_length=1000)


@router.post(
    "/captions/refresh",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_caption_refresh(
    payload: CaptionRefreshRequest,
    _: Annotated[User, Depends(require_admin)],
) -> TaskStatusResponse:
    video_ids = list(dict.fromkeys(str(video_id) for video_id in (payload.video_ids or [])))
    task_id = str(uuid4())
    task_label = (
        f"caption-refresh:{len(video_ids)}-videos" if video_ids else "caption-refresh:all-fallbacks"
    )
    record = await create_task_status(
        task_id,
        task_label,
        celery_task_id=task_id,
        pipeline_version="caption-refresh-v1",
    )
    try:
        await asyncio.to_thread(
            refresh_fallback_captions.apply_async,
            kwargs={"task_id": task_id, "video_ids": video_ids or None},
            task_id=task_id,
        )
    except Exception as exc:
        await update_task_status(
            task_id,
            TaskStatus.FAILED,
            progress=0,
            error="Unable to enqueue caption refresh task",
            error_code="enqueue_failed",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to enqueue caption refresh task",
        ) from exc
    return record


@router.get("/telemetry", response_model=AdminTelemetry)
async def get_telemetry(_: Annotated[User, Depends(require_admin)]) -> AdminTelemetry:
    return await collect_telemetry()


@router.get("/eval", response_model=EvalReportResponse)
async def get_eval_report(_: Annotated[User, Depends(require_admin)]) -> EvalReportResponse:
    return load_eval_report()


@router.get("/embedding-model", response_model=EmbeddingModelStatus)
async def get_embedding_model_status(
    _: Annotated[User, Depends(require_admin)],
) -> EmbeddingModelStatus:
    return await embedding_model_request("status")


@router.post("/embedding-model/load", response_model=EmbeddingModelStatus)
async def load_embedding_model(
    _: Annotated[User, Depends(require_admin)],
) -> EmbeddingModelStatus:
    return await embedding_model_request("load")


@router.post("/embedding-model/unload", response_model=EmbeddingModelStatus)
async def unload_embedding_model(
    _: Annotated[User, Depends(require_admin)],
) -> EmbeddingModelStatus:
    return await embedding_model_request("unload")


@router.get("/traces")
async def get_system_traces(
    _: Annotated[User, Depends(require_admin)],
    limit: int = 50,
    trace_type: str | None = None,
) -> dict[str, Any]:
    from core.tracer import get_tracer

    tracer = get_tracer()
    return {
        "stats": tracer.get_summary_stats(),
        "traces": tracer.get_recent(limit=limit, trace_type=trace_type),
    }


@router.get("/traces/{trace_id}")
async def get_system_trace_detail(
    trace_id: str,
    _: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    from fastapi import HTTPException

    from core.tracer import get_tracer

    trace = get_tracer().get_by_id(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace


@router.delete("/traces")
async def clear_system_traces(
    _: Annotated[User, Depends(require_admin)],
) -> dict[str, str]:
    from core.tracer import get_tracer

    get_tracer().clear()
    return {"status": "cleared"}
