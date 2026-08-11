"""Redis/PostgreSQL persistence for ingestion-task state."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import text

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
    redis = get_redis_client()
    await redis.hset(_key(record.task_id), mapping=_redis_mapping(record))
    await redis.expire(_key(record.task_id), _TTL_SECONDS)


async def _create_postgres(record: TaskStatusResponse) -> None:
    async with get_session_factory()() as session:
        await session.execute(
            text(
                """
                INSERT INTO ingestion_tasks
                    (task_id, video_path, status, progress, created_at, updated_at)
                VALUES (:task_id, :video_path, :status, :progress, :created_at, :updated_at)
                """
            ),
            {
                "task_id": UUID(record.task_id),
                "video_path": record.video_path,
                "status": record.status.value,
                "progress": record.progress,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            },
        )
        await session.commit()


async def _update_redis(task_id: str, updates: dict[str, Any]) -> None:
    redis = get_redis_client()
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
        pipeline.expire(_key(task_id), _TTL_SECONDS)
        await pipeline.execute()


async def _update_postgres(task_id: str, updates: dict[str, Any]) -> None:
    async with get_session_factory()() as session:
        result = await session.execute(
            text(
                """
                UPDATE ingestion_tasks
                SET status = :status, progress = :progress,
                    result = CAST(:result AS JSONB),
                    error = :error, updated_at = :updated_at
                WHERE task_id = :task_id
                """
            ),
            {
                "task_id": UUID(task_id),
                "status": updates["status"],
                "progress": updates["progress"],
                "result": json.dumps(updates["result"]) if updates["result"] is not None else None,
                "error": updates["error"],
                "updated_at": updates["updated_at"],
            },
        )
        if result.rowcount != 1:
            await session.rollback()
            raise TaskStatusStoreError(f"PostgreSQL task {task_id} does not exist")
        await session.commit()


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


async def create_task_status(task_id: str, video_path: str) -> TaskStatusResponse:
    now = datetime.now(UTC)
    record = TaskStatusResponse(
        task_id=task_id,
        video_path=video_path,
        status=TaskStatus.QUEUED,
        progress=0,
        created_at=now,
        updated_at=now,
    )
    results = list(
        await asyncio.gather(
            _create_redis(record),
            _create_postgres(record),
            return_exceptions=True,
        )
    )
    _log_write_failures(task_id, "create", results)
    _raise_if_all_writes_failed("create", results)
    return record


async def update_task_status(
    task_id: str,
    status: TaskStatus,
    *,
    progress: int,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    if not 0 <= progress <= 100:
        raise ValueError("progress must be between 0 and 100")
    updated_at = datetime.now(UTC)
    updates: dict[str, Any] = {
        "status": status.value,
        "progress": progress,
        "updated_at": updated_at,
        "result": result,
        "error": error,
    }
    results = list(
        await asyncio.gather(
            _update_redis(task_id, updates),
            _update_postgres(task_id, updates),
            return_exceptions=True,
        )
    )
    _log_write_failures(task_id, "update", results)
    _raise_if_all_writes_failed("update", results)


async def get_task_status(task_id: str) -> TaskStatusResponse | None:
    """Read task status from Redis, falling back to PostgreSQL."""

    redis_error: Exception | None = None
    try:
        data = await get_redis_client().hgetall(_key(task_id))
        if data:
            return _decode_redis_record(data)
    except Exception as exc:
        redis_error = exc
        logger.warning(
            "Failed to read task {task_id} from Redis: {error}", task_id=task_id, error=exc
        )

    try:
        async with get_session_factory()() as session:
            result = await session.execute(
                text(
                    """
                    SELECT task_id, video_path, status, progress, result, error,
                           created_at, updated_at
                    FROM ingestion_tasks WHERE task_id = :task_id
                    """
                ),
                {"task_id": UUID(task_id)},
            )
            row = result.mappings().one_or_none()
            return TaskStatusResponse.model_validate(dict(row)) if row else None
    except Exception as postgres_error:
        logger.warning(
            "Failed to read task {task_id} from PostgreSQL: {error}",
            task_id=task_id,
            error=postgres_error,
        )
        if redis_error is not None:
            raise TaskStatusStoreError(
                "Failed to read task status from Redis and PostgreSQL"
            ) from postgres_error
        return None


__all__ = [
    "TaskStatusStoreError",
    "create_task_status",
    "get_task_status",
    "update_task_status",
]
