"""Celery task adapter for refreshing old fallback captions."""

from __future__ import annotations

import asyncio
from typing import Any

from celery import Task
from loguru import logger

from infrastructure.postgres import close_postgres
from infrastructure.qdrant import close_qdrant
from infrastructure.redis import close_redis
from repositories.task_status import TaskStatusStoreError, update_task_status
from schemas.task import TaskStatus
from services.caption_refresh import refresh_fallback_captions as refresh_payloads
from worker.celery_app import celery_app
from worker.task_names import CAPTION_REFRESH_TASK_NAME


async def _run_refresh(
    task: Task,
    task_id: str,
    video_ids: list[str] | None,
) -> dict[str, Any]:
    await update_task_status(task_id, TaskStatus.PROCESSING, progress=1)

    async def progress(value: int) -> None:
        applied = await update_task_status(
            task_id, TaskStatus.PROCESSING, progress=max(1, min(value, 99))
        )
        if applied is False:
            raise RuntimeError("Caption refresh task was cancelled")
        task.update_state(state="PROGRESS", meta={"progress": value, "stage": "caption_refresh"})

    try:
        result = await refresh_payloads(
            video_ids=set(video_ids) if video_ids else None,
            progress=progress,
        )
        await update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100,
            result=result,
        )
        logger.info(
            "Caption refresh task {task_id} completed: {result}", task_id=task_id, result=result
        )
        return result
    except Exception as exc:
        logger.exception("Caption refresh task {task_id} failed", task_id=task_id)
        try:
            await update_task_status(
                task_id,
                TaskStatus.FAILED,
                progress=0,
                error=str(exc),
                error_code="caption_refresh_failed",
            )
        except Exception:
            logger.exception(
                "Could not persist caption refresh failure for {task_id}", task_id=task_id
            )
        raise


@celery_app.task(
    bind=True,
    name=CAPTION_REFRESH_TASK_NAME,
    autoretry_for=(ConnectionError, TaskStatusStoreError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def refresh_fallback_captions(
    task: Task,
    task_id: str,
    video_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Regenerate fallback captions from derived thumbnails, without re-embedding."""

    async def run_and_close() -> dict[str, Any]:
        try:
            return await _run_refresh(task, task_id, video_ids)
        finally:
            results = await asyncio.gather(
                close_redis(), close_postgres(), close_qdrant(), return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    logger.error(
                        "Caption refresh infrastructure cleanup failed: {error}", error=result
                    )

    return asyncio.run(run_and_close())


__all__ = ["refresh_fallback_captions"]
