from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from api.v1.ingestion import (
    _celery_fallback,
    delete_video,
    upload_and_create_ingestion_task,
)
from repositories.corpus import VideoDeletionPlan
from schemas.task import TaskStatus


def test_celery_fallback_clamps_invalid_progress() -> None:
    result = SimpleNamespace(
        state="PROGRESS",
        info={"progress": 999},
        result=None,
        successful=lambda: False,
        failed=lambda: False,
    )

    with patch("api.v1.ingestion.AsyncResult", return_value=result):
        response = _celery_fallback("11111111-1111-4111-8111-111111111111")

    assert response is not None
    assert response.status == TaskStatus.PROCESSING
    assert response.progress == 100


@pytest.mark.asyncio
async def test_failed_video_can_be_claimed_and_requeued() -> None:
    video_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    task_id = "11111111-1111-4111-8111-111111111111"

    class Upload:
        filename = "video.mp4"
        content_type = "video/mp4"

        def __init__(self):
            self.remaining = b"video-bytes"

        async def read(self, _size):
            chunk, self.remaining = self.remaining, b""
            return chunk

        async def close(self):
            return None

    upload = Upload()
    record = SimpleNamespace(task_id=task_id)

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("api.v1.ingestion.asyncio.to_thread", run_inline),
        patch("api.v1.ingestion.get_raw_storage"),
        patch("api.v1.ingestion.corpus.upsert_video", AsyncMock(return_value=(video_id, False))),
        patch("api.v1.ingestion.corpus.is_video_indexed", AsyncMock(return_value=False)),
        patch("api.v1.ingestion.corpus.set_video_assets", AsyncMock()),
        patch(
            "api.v1.ingestion.corpus.claim_video_ingestion",
            AsyncMock(return_value=True),
        ) as claim,
        patch("api.v1.ingestion.create_task_status", AsyncMock(return_value=record)),
        patch("api.v1.ingestion.process_video_ingestion.apply_async") as enqueue,
    ):
        result = await upload_and_create_ingestion_task(upload)

    assert result is record
    claim.assert_awaited_once()
    enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_delete_video_revokes_task_and_removes_all_artifacts() -> None:
    video_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    plan = VideoDeletionPlan(
        celery_task_ids=("11111111-1111-4111-8111-111111111111",),
    )
    raw = SimpleNamespace(delete_prefix=Mock())
    derived = SimpleNamespace(delete_prefix=Mock())

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("api.v1.ingestion.asyncio.to_thread", run_inline),
        patch("api.v1.ingestion.corpus.prepare_video_deletion", AsyncMock(return_value=plan)),
        patch("api.v1.ingestion.corpus.cancel_video_tasks", AsyncMock()) as cancel,
        patch("api.v1.ingestion.corpus.delete_video", AsyncMock()) as delete_row,
        patch("api.v1.ingestion.delete_by_video", AsyncMock()) as delete_vectors,
        patch("api.v1.ingestion.get_raw_storage", return_value=raw),
        patch("api.v1.ingestion.get_derived_storage", return_value=derived),
        patch("api.v1.ingestion.celery_app.control.revoke") as revoke,
    ):
        await delete_video(video_id)

    revoke.assert_called_once_with(plan.celery_task_ids[0], terminate=False)
    cancel.assert_awaited_once()
    delete_vectors.assert_awaited_once_with(video_id)
    raw.delete_prefix.assert_called_once_with(f"raw/{video_id}/")
    assert derived.delete_prefix.call_args_list == [
        call(f"videos/{video_id}/"),
        call(f"thumbnails/{video_id}/"),
    ]
    delete_row.assert_awaited_once()
