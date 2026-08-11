from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from repositories.task_status import TaskStatusStoreError
from schemas.task import TaskStatus
from worker.tasks import ingestion

TASK_ID = "11111111-1111-4111-8111-111111111111"


def test_mock_embedding_digest_is_deterministic() -> None:
    first = ingestion._mock_embedding_digest(TASK_ID, "/video.mp4", 5)
    second = ingestion._mock_embedding_digest(TASK_ID, "/video.mp4", 5)

    assert first == second
    assert len(first) == 64


@pytest.mark.asyncio
async def test_store_failure_marks_task_for_retry() -> None:
    task = SimpleNamespace(update_state=lambda **_: None)
    error = TaskStatusStoreError("stores unavailable")

    with (
        patch.object(ingestion, "_report_progress", AsyncMock(side_effect=error)),
        patch.object(ingestion, "update_task_status", AsyncMock()) as update,
        pytest.raises(TaskStatusStoreError),
    ):
        await ingestion._run_ingestion(task, TASK_ID, "/video.mp4")

    update.assert_awaited_once_with(
        TASK_ID,
        TaskStatus.RETRYING,
        progress=0,
        error="stores unavailable",
    )
