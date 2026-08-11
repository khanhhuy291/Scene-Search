"""Stable Celery task identifiers shared by registration and routing."""

INGESTION_TASK_NAME = "worker.tasks.ingestion.process_video_ingestion"

__all__ = ["INGESTION_TASK_NAME"]
