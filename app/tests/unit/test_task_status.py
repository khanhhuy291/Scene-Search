from unittest.mock import AsyncMock, patch

import pytest

from repositories.task_status import TaskStatusStoreError, get_task_status, update_task_status
from schemas.task import TaskStatus


class _BrokenRedis:
    hgetall = AsyncMock(side_effect=ConnectionError("redis unavailable"))


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
