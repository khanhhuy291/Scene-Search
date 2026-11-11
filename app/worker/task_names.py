"""Stable Celery task identifiers shared by registration and routing."""

INGESTION_TASK_NAME = "worker.tasks.ingestion.process_video_ingestion"
CAPTION_REFRESH_TASK_NAME = "worker.tasks.caption_refresh.refresh_fallback_captions"

__all__ = ["CAPTION_REFRESH_TASK_NAME", "INGESTION_TASK_NAME"]
