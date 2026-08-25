from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.sqltypes import String

from repositories.task_status import (
    TaskStatusStoreError,
    _reported_rowcount,
    _update_postgres,
    get_task_status,
    update_task_status,
)
from schemas.task import TaskStatus


class _BrokenRedis:
    hgetall = AsyncMock(side_effect=ConnectionError("redis unavailable"))


class _UpdateResult:
    def __init__(self, rowcount: object = 1) -> None:
        self.rowcount = rowcount


class _CapturingSession:
    def __init__(self, rowcount: object = 1) -> None:
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.rowcount = rowcount

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, statement):
        self.statements.append(statement)
        return _UpdateResult(self.rowcount)

    async def scalar(self, statement):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_get_status_raises_when_both_stores_are_unavailable() -> None:
    with (
        patch("repositories.task_status.get_redis_client", return_value=_BrokenRedis()),
        patch(
            "repositories.task_status.get_session_factory",
            side_effect=ConnectionError("postgres unavailable"),
        ),
        pytest.raises(TaskStatusStoreError),
    ):
        await get_task_status("11111111-1111-4111-8111-111111111111")


@pytest.mark.asyncio
async def test_update_succeeds_when_one_store_is_available() -> None:
    with (
        patch(
            "repositories.task_status._update_redis",
            AsyncMock(side_effect=ConnectionError("redis unavailable")),
        ),
        patch("repositories.task_status._update_postgres", AsyncMock()),
    ):
        await update_task_status(
            "11111111-1111-4111-8111-111111111111",
            TaskStatus.PROCESSING,
            progress=40,
        )


@pytest.mark.asyncio
async def test_update_raises_when_both_stores_are_unavailable() -> None:
    with (
        patch(
            "repositories.task_status._update_redis",
            AsyncMock(side_effect=ConnectionError("redis unavailable")),
        ),
        patch(
            "repositories.task_status._update_postgres",
            AsyncMock(side_effect=ConnectionError("postgres unavailable")),
        ),
        pytest.raises(TaskStatusStoreError),
    ):
        await update_task_status(
            "11111111-1111-4111-8111-111111111111",
            TaskStatus.PROCESSING,
            progress=40,
        )


@pytest.mark.asyncio
async def test_postgres_update_uses_typed_status_and_idempotent_lifecycle_expression() -> None:
    """Regression for asyncpg text-versus-varchar AmbiguousParameterError."""
    session = _CapturingSession()
    timestamp = datetime.now(UTC)
    updates = {
        "status": TaskStatus.PROCESSING.value,
        "progress": 40,
        "result": {"stage": "embedding"},
        "error": None,
        "error_code": None,
        "updated_at": timestamp,
    }
    with patch(
        "repositories.task_status.get_session_factory",
        return_value=_SessionFactory(session),
    ):
        # Repeating the same transition must remain valid and must not replace
        # the original started_at value.
        await _update_postgres("11111111-1111-4111-8111-111111111111", updates)
        await _update_postgres("11111111-1111-4111-8111-111111111111", updates)

    assert session.commits == 2
    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    status_binds = [
        bind for bind in compiled.binds.values() if bind.value == TaskStatus.PROCESSING.value
    ]
    assert status_binds
    assert all(isinstance(bind.type, String) and bind.type.length == 32 for bind in status_binds)
    sql = str(compiled)
    assert "CASE" not in sql
    assert "coalesce(ingestion_tasks.started_at" in sql


@pytest.mark.asyncio
async def test_cancelled_task_ignores_late_worker_update() -> None:
    with (
        patch("repositories.task_status._update_postgres", AsyncMock(return_value=False)),
        patch("repositories.task_status._update_redis", AsyncMock()) as redis_update,
    ):
        applied = await update_task_status(
            "11111111-1111-4111-8111-111111111111",
            TaskStatus.COMPLETED,
            progress=100,
        )

    assert applied is False
    redis_update.assert_not_awaited()


def test_reported_rowcount_accepts_only_non_negative_ints() -> None:
    assert _reported_rowcount(_UpdateResult(1)) == 1
    assert _reported_rowcount(_UpdateResult(0)) == 0
    assert _reported_rowcount(_UpdateResult(-1)) is None
    assert _reported_rowcount(_UpdateResult(True)) is None
    assert _reported_rowcount(_UpdateResult("1")) is None
    assert _reported_rowcount(object()) is None


@pytest.mark.asyncio
async def test_postgres_update_rejects_a_missing_row() -> None:
    session = _CapturingSession(rowcount=0)
    updates = {
        "status": TaskStatus.PROCESSING.value,
        "progress": 40,
        "result": None,
        "error": None,
        "error_code": None,
        "updated_at": datetime.now(UTC),
    }
    with (
        patch(
            "repositories.task_status.get_session_factory",
            return_value=_SessionFactory(session),
        ),
        pytest.raises(TaskStatusStoreError, match="does not exist"),
    ):
        await _update_postgres("11111111-1111-4111-8111-111111111111", updates)
    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_postgres_update_commits_when_rowcount_is_unavailable() -> None:
    session = _CapturingSession(rowcount=-1)
    updates = {
        "status": TaskStatus.PROCESSING.value,
        "progress": 40,
        "result": None,
        "error": None,
        "error_code": None,
        "updated_at": datetime.now(UTC),
    }
    with patch(
        "repositories.task_status.get_session_factory",
        return_value=_SessionFactory(session),
    ):
        await _update_postgres("11111111-1111-4111-8111-111111111111", updates)
    assert session.commits == 1
    assert session.rollbacks == 0
