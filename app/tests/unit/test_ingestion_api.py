from types import SimpleNamespace
from unittest.mock import patch

from api.v1.ingestion import _celery_fallback
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
