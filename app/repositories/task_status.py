"""Redis/PostgreSQL persistence for ingestion-task state."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select, text, update

from db.models.ingestion_task import IngestionTask
from infrastructure.postgres import get_session_factory
from infrastructure.redis import get_redis_client
from schemas.task import TaskStatus, TaskStatusResponse

_KEY_PREFIX = "scenesearch:ingestion-task:"
_TTL_SECONDS = 7 * 24 * 60 * 60


class TaskStatusStoreError(RuntimeError):
    """Raised when no configured status store can complete an operation."""


def _key(task_id: str) -> str:
    return f"{_KEY_PREFIX}{task_id}"


def _redis_mapping(record: TaskStatusResponse) -> dict[str, str]:
    payload = record.model_dump(mode="json")
    return {
        field: json.dumps(value, separators=(",", ":"))
        for field, value in payload.items()
        if value is not None
    }


def _decode_redis_record(data: dict[str, str]) -> TaskStatusResponse:
    return TaskStatusResponse.model_validate(
        {key: json.loads(value) for key, value in data.items()}
    )


def _raise_if_all_writes_failed(operation: str, results: list[object]) -> None:
    failures = [result for result in results if isinstance(result, BaseException)]
    if len(failures) != len(results):
        return
    raise TaskStatusStoreError(
        f"Failed to {operation} task status in Redis and PostgreSQL"
    ) from failures[-1]


async def _create_redis(record: TaskStatusResponse) -> None:
    redis: Any = get_redis_client()
    await redis.hset(_key(record.task_id), mapping=_redis_mapping(record))
    await redis.expire(_key(record.task_id), _TTL_SECONDS)


async def _create_postgres(record: TaskStatusResponse) -> None:
    async with get_session_factory()() as session:
        await session.execute(
            text(
                """
                INSERT INTO ingestion_tasks
                    (task_id, video_path, status, progress, video_id, celery_task_id,
                     pipeline_version, created_at, updated_at)
                VALUES (:task_id, :video_path, :status, :progress, :video_id,
                        :celery_task_id, :pipeline_version, :created_at, :updated_at)
                """
            ),
            {
                "task_id": UUID(record.task_id),
                "video_path": record.video_path,
                "status": record.status.value,
                "progress": record.progress,
                "video_id": UUID(record.video_id) if record.video_id else None,
                "celery_task_id": record.celery_task_id,
                "pipeline_version": record.pipeline_version,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            },
        )
        await session.commit()


async def _update_redis(task_id: str, updates: dict[str, Any]) -> None:
    redis: Any = get_redis_client()
    mapping = {
        "task_id": json.dumps(task_id),
        **{
            key: json.dumps(
                value.isoformat() if isinstance(value, datetime) else value,
                separators=(",", ":"),
            )
            for key, value in updates.items()
            if value is not None
        },
    }
    async with redis.pipeline(transaction=True) as pipeline:
        pipeline.hset(_key(task_id), mapping=mapping)
        if updates.get("result") is None:
            pipeline.hdel(_key(task_id), "result")
        if updates.get("error") is None:
            pipeline.hdel(_key(task_id), "error")
        if updates.get("error_code") is None:
            pipeline.hdel(_key(task_id), "error_code")
        pipeline.expire(_key(task_id), _TTL_SECONDS)
        await pipeline.execute()


def _reported_rowcount(result: object) -> int | None:
    """Return a driver-reported UPDATE count, or None when the count is unusable.

    SQLAlchemy documents ``rowcount == -1`` when the dialect cannot report it.
    ``bool`` is a subclass of ``int``, so it is excluded before the int check.
    """

    raw = getattr(result, "rowcount", None)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    if raw < 0:
        return None
    return raw


async def _update_postgres(task_id: str, updates: dict[str, Any]) -> bool:
    values: dict[str, Any] = {
        "status": updates["status"],
        "progress": updates["progress"],
        "result": updates["result"],
        "error": updates["error"],
        "error_code": updates["error_code"],
        "updated_at": updates["updated_at"],
    }
    # Choose the transition expression before compiling SQL. This avoids one
    # untyped bind being reused as both VARCHAR assignment data and TEXT CASE
    # comparison data (asyncpg's AmbiguousParameterError). COALESCE makes
    # repeated processing/terminal updates idempotent for lifecycle timestamps.
    if updates["status"] == TaskStatus.PROCESSING.value:
        values["started_at"] = func.coalesce(IngestionTask.started_at, updates["updated_at"])
    elif updates["status"] in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}:
        values["finished_at"] = func.coalesce(IngestionTask.finished_at, updates["updated_at"])

    task_uuid = UUID(task_id)
    statement = (
        update(IngestionTask)
        .where(
            IngestionTask.task_id == task_uuid,
            IngestionTask.status != TaskStatus.CANCELLED.value,
        )
        .values(**values)
    )
    async with get_session_factory()() as session:
        result = await session.execute(statement)
        rowcount = _reported_rowcount(result)
        if rowcount is None:
            logger.warning(
                "PostgreSQL UPDATE for task {task_id} did not report a usable rowcount; committing",
                task_id=task_id,
            )
        elif rowcount != 1:
            current = await session.scalar(
                select(IngestionTask.status).where(IngestionTask.task_id == task_uuid)
            )
            if current == TaskStatus.CANCELLED.value:
                await session.rollback()
                return False
            await session.rollback()
            raise TaskStatusStoreError(f"PostgreSQL task {task_id} does not exist")
        await session.commit()
        return True


def _log_write_failures(task_id: str, operation: str, results: list[object]) -> None:
    for backend, result in zip(("Redis", "PostgreSQL"), results, strict=True):
        if isinstance(result, BaseException):
            logger.error(
                "Failed to {operation} task {task_id} in {backend}: {error}",
                operation=operation,
                task_id=task_id,
                backend=backend,
                error=result,
            )


async def create_task_status(
    task_id: str,
    video_path: str,
    *,
    video_id: str | None = None,
    celery_task_id: str | None = None,
    pipeline_version: str | None = None,
) -> TaskStatusResponse:
    now = datetime.now(UTC)
    record = TaskStatusResponse(
        task_id=task_id,
        video_path=video_path,
        status=TaskStatus.QUEUED,
        progress=0,
        video_id=video_id,
        celery_task_id=celery_task_id,
        pipeline_version=pipeline_version,
        created_at=now,
        updated_at=now,
    )
    try:
        await _create_postgres(record)
    except Exception as exc:
        raise TaskStatusStoreError("Failed to create authoritative PostgreSQL status") from exc
    redis_result = await asyncio.gather(_create_redis(record), return_exceptions=True)
    if isinstance(redis_result[0], BaseException):
        logger.warning("Failed to cache created task {task_id} in Redis", task_id=task_id)
    return record


async def update_task_status(
    task_id: str,
    status: TaskStatus,
    *,
    progress: int,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    error_code: str | None = None,
) -> bool:
    if not 0 <= progress <= 100:
        raise ValueError("progress must be between 0 and 100")
    updated_at = datetime.now(UTC)
    updates: dict[str, Any] = {
        "status": status.value,
        "progress": progress,
        "updated_at": updated_at,
        "result": result,
        "error": error,
        "error_code": error_code,
    }
    try:
        applied = await _update_postgres(task_id, updates)
    except Exception as exc:
        raise TaskStatusStoreError("Failed to update authoritative PostgreSQL status") from exc
    if applied is False:
        return False
    redis_result = await asyncio.gather(_update_redis(task_id, updates), return_exceptions=True)
    if isinstance(redis_result[0], BaseException):
        logger.warning("Failed to refresh task {task_id} in Redis", task_id=task_id)
    return True


async def get_task_status(task_id: str) -> TaskStatusResponse | None:
    """Read authoritative PostgreSQL state, falling back to the Redis cache."""

    postgres_error: Exception | None = None
    try:
        async with get_session_factory()() as session:
            result = await session.execute(
                text(
                    """
                    SELECT task_id, video_path, status, progress, result, error,
                           error_code, video_id, celery_task_id, pipeline_version,
                           started_at, finished_at, created_at, updated_at
                    FROM ingestion_tasks WHERE task_id = :task_id
                    """
                ),
                {"task_id": UUID(task_id)},
            )
            row = result.mappings().one_or_none()
            if row:
                return TaskStatusResponse.model_validate(dict(row))
    except Exception as exc:
        postgres_error = exc
        logger.warning(
            "Failed to read task {task_id} from PostgreSQL: {error}", task_id=task_id, error=exc
        )

    try:
        redis: Any = get_redis_client()
        data = await redis.hgetall(_key(task_id))
        return _decode_redis_record(data) if data else None
    except Exception as redis_error:
        logger.warning(
            "Failed to read task {task_id} from Redis: {error}",
            task_id=task_id,
            error=redis_error,
        )
        if postgres_error is not None:
            raise TaskStatusStoreError(
                "Failed to read task status from PostgreSQL and Redis"
            ) from redis_error
        return None


async def list_task_statuses(
    *, limit: int = 25, offset: int = 0, status: TaskStatus | None = None
) -> tuple[list[TaskStatusResponse], int]:
    """List durable jobs from PostgreSQL; Redis is never authoritative here."""
    where = "WHERE status = :status" if status is not None else ""
    parameters: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "status": status.value if status is not None else None,
    }
    async with get_session_factory()() as session:
        total = await session.scalar(
            text(f"SELECT COUNT(*) FROM ingestion_tasks {where}"), parameters
        )
        result = await session.execute(
            text(
                f"""
                SELECT task_id, video_path, status, progress, result, error,
                       error_code, video_id, celery_task_id, pipeline_version,
                       started_at, finished_at, created_at, updated_at
                FROM ingestion_tasks
                {where}
                ORDER BY created_at DESC, task_id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            parameters,
        )
    return (
        [TaskStatusResponse.model_validate(dict(row)) for row in result.mappings()],
        int(total or 0),
    )


__all__ = [
    "TaskStatusStoreError",
    "create_task_status",
    "get_task_status",
    "list_task_statuses",
    "update_task_status",
]
