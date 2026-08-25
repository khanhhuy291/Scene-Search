from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from pipelines.common.errors import VideoValidationError
from repositories.task_status import TaskStatusStoreError
from schemas.task import TaskStatus
from worker.tasks import ingestion

TASK_ID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
async def test_task_persists_real_service_result() -> None:
    task = SimpleNamespace(update_state=lambda **_: None)
    result = {"video_id": "video-id", "scenes_indexed": 1, "vectors_indexed": 1}

    with (
        patch.object(ingestion, "run_ingestion_pipeline", AsyncMock(return_value=result)),
        patch.object(ingestion, "update_task_status", AsyncMock()) as update,
    ):
        payload = await ingestion._run_ingestion(task, TASK_ID, "video-id")

    assert payload["vectors_indexed"] == 1
    update.assert_awaited_once_with(
        TASK_ID,
        TaskStatus.COMPLETED,
        progress=100,
        result=payload,
    )


@pytest.mark.asyncio
async def test_store_failure_marks_task_for_retry() -> None:
    task = SimpleNamespace(update_state=lambda **_: None)
    error = TaskStatusStoreError("stores unavailable")

    async def run_service(*, job_id, video_id, progress):
        await progress(5, "checksumming")

    with (
        patch.object(ingestion, "run_ingestion_pipeline", run_service),
        patch.object(ingestion, "_report_progress", AsyncMock(side_effect=error)),
        patch.object(ingestion, "update_task_status", AsyncMock()) as update,
        pytest.raises(TaskStatusStoreError),
    ):
        await ingestion._run_ingestion(task, TASK_ID, "video-id")

    update.assert_awaited_once_with(
        TASK_ID,
        TaskStatus.RETRYING,
        progress=0,
        error="stores unavailable",
    )


@pytest.mark.asyncio
async def test_permanent_failure_marks_video_and_task_failed() -> None:
    task = SimpleNamespace(update_state=lambda **_: None, request=SimpleNamespace(retries=0))
    error = VideoValidationError("invalid video", stage="validate")

    with (
        patch.object(ingestion, "run_ingestion_pipeline", AsyncMock(side_effect=error)),
        patch.object(ingestion.corpus, "mark_video_ingestion_failed", AsyncMock()) as mark,
        patch.object(ingestion, "update_task_status", AsyncMock()) as update,
        pytest.raises(VideoValidationError),
    ):
        await ingestion._run_ingestion(task, TASK_ID, TASK_ID)

    mark.assert_awaited_once()
    update.assert_awaited_once_with(
        TASK_ID,
        TaskStatus.FAILED,
        progress=0,
        error="invalid video",
    )
