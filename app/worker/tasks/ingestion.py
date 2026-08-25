"""Celery adapter for the real ingestion application service."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from celery import Task
from loguru import logger

from infrastructure.postgres import close_postgres
from infrastructure.qdrant import close_qdrant
from infrastructure.redis import close_redis
from pipelines.common.errors import IngestionCancelledError, RetryablePipelineError
from pipelines.ingestion.orchestrator import run_ingestion_pipeline
from repositories import corpus
from repositories.task_status import TaskStatusStoreError, update_task_status
from schemas.task import TaskStatus
from worker.celery_app import celery_app
from worker.task_names import INGESTION_TASK_NAME


async def _report_progress(
    task: Task,
    task_id: str,
    *,
    progress: int,
    stage: str,
) -> None:
    applied = await update_task_status(task_id, TaskStatus.PROCESSING, progress=progress)
    if applied is False:
        raise IngestionCancelledError("Video ingestion was cancelled", stage=stage)
    task.update_state(state="PROGRESS", meta={"progress": progress, "stage": stage})


async def _run_ingestion(
    task: Task,
    task_id: str,
    video_id: str,
) -> dict[str, Any]:
    logger.info(
        "Starting video ingestion task {task_id} for {video_path}",
        task_id=task_id,
        video_path="minio",
    )
    try:

        async def progress(value: int, stage: str) -> None:
            await _report_progress(task, task_id, progress=value, stage=stage)

        result = await run_ingestion_pipeline(job_id=task_id, video_id=video_id, progress=progress)
        await update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100,
            result=result,
        )
        logger.info("Completed video ingestion task {task_id}", task_id=task_id)
        return result
    except Exception as exc:
        logger.exception("Video ingestion task {task_id} failed", task_id=task_id)
        retryable = isinstance(exc, (RetryablePipelineError, ConnectionError, TaskStatusStoreError))
        retries = getattr(getattr(task, "request", None), "retries", 0)
        max_retries = getattr(task, "max_retries", 3)
        exhausted = retries >= max_retries
        failure_status = TaskStatus.RETRYING if retryable and not exhausted else TaskStatus.FAILED
        if failure_status is TaskStatus.FAILED:
            try:
                await corpus.mark_video_ingestion_failed(UUID(video_id))
            except Exception:
                logger.exception("Could not mark video {video_id} as failed", video_id=video_id)
        try:
            await update_task_status(
                task_id,
                failure_status,
                progress=0,
                error=str(exc),
            )
        except Exception:
            logger.exception("Could not persist failure state for task {task_id}", task_id=task_id)
        raise


@celery_app.task(
    bind=True,
    name=INGESTION_TASK_NAME,
    autoretry_for=(RetryablePipelineError, ConnectionError, TaskStatusStoreError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_video_ingestion(
    task: Task,
    task_id: str,
    video_id: str,
) -> dict[str, Any]:
    """Run real media ingestion and persist its task status."""

    async def run_and_close() -> dict[str, Any]:
        try:
            return await _run_ingestion(task, task_id, video_id)
        finally:
            results = await asyncio.gather(
                close_redis(),
                close_postgres(),
                close_qdrant(),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    logger.error("Worker infrastructure cleanup failed: {error}", error=result)

    return asyncio.run(run_and_close())


__all__ = ["process_video_ingestion"]
