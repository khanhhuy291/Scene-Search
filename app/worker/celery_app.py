"""Celery application used by SceneSearch workers."""

from celery import Celery, bootsteps
from loguru import logger

from core.config import get_settings
from ml.privacy_weights import resolve_privacy_weights
from worker.task_names import CAPTION_REFRESH_TASK_NAME, INGESTION_TASK_NAME

settings = get_settings().celery

celery_app = Celery(
    "scenesearch",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["worker.tasks.ingestion", "worker.tasks.caption_refresh"],
)

celery_app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    enable_utc=True,
    result_accept_content=["json"],
    result_expires=settings.result_expires,
    result_serializer="json",
    task_acks_late=True,
    task_default_queue="default",
    task_reject_on_worker_lost=True,
    task_routes={
        INGESTION_TASK_NAME: {
            "queue": "ingestion",
            "routing_key": "ingestion.video",
        },
        CAPTION_REFRESH_TASK_NAME: {
            "queue": "ingestion",
            "routing_key": "ingestion.caption_refresh",
        },
    },
    task_serializer="json",
    task_soft_time_limit=settings.task_soft_time_limit,
    task_time_limit=settings.task_time_limit,
    task_track_started=True,
    timezone="UTC",
    worker_concurrency=settings.worker_concurrency,
    worker_max_tasks_per_child=50,
    worker_prefetch_multiplier=settings.worker_prefetch_multiplier,
)


class PreparePrivacyWeights(bootsteps.StartStopStep):
    """Prepare YOLO weights before consuming jobs."""

    def start(self, worker) -> None:
        weights = resolve_privacy_weights(get_settings().ml)
        logger.info("YOLO privacy checkpoint ready at {path}", path=weights)


celery_app.steps["worker"].add(PreparePrivacyWeights)


__all__ = ["celery_app"]
