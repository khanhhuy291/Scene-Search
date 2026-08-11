from worker.celery_app import celery_app
from worker.task_names import INGESTION_TASK_NAME
from worker.tasks.ingestion import process_video_ingestion


def test_ingestion_task_registration_matches_route() -> None:
    assert process_video_ingestion.name == INGESTION_TASK_NAME
    assert INGESTION_TASK_NAME in celery_app.conf.task_routes
    assert celery_app.conf.task_routes[INGESTION_TASK_NAME]["queue"] == "ingestion"
