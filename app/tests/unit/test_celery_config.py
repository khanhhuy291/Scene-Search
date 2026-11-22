import pytest
from celery.worker.components import Consumer

from worker.celery_app import PreparePrivacyWeights, celery_app
from worker.task_names import INGESTION_TASK_NAME
from worker.tasks.ingestion import process_video_ingestion


def test_ingestion_task_registration_matches_route() -> None:
    assert process_video_ingestion.name == INGESTION_TASK_NAME
    assert INGESTION_TASK_NAME in celery_app.conf.task_routes
    assert celery_app.conf.task_routes[INGESTION_TASK_NAME]["queue"] == "ingestion"


def test_worker_prepares_privacy_weights_before_consuming(monkeypatch) -> None:
    def fail(_settings):
        raise ValueError("invalid checksum")

    monkeypatch.setattr("worker.celery_app.resolve_privacy_weights", fail)
    worker = celery_app.WorkController(pool="solo")
    steps = list(worker.blueprint.order)
    preparation = next(step for step in steps if isinstance(step, PreparePrivacyWeights))
    consumer = next(step for step in steps if isinstance(step, Consumer))
    assert steps.index(preparation) < steps.index(consumer)
    with pytest.raises(ValueError, match="invalid checksum"):
        preparation.start(worker)
