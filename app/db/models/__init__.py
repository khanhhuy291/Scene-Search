"""SQLAlchemy models included in Alembic metadata."""

from db.models.base import Base
from db.models.ingestion_task import IngestionTask

__all__ = ["Base", "IngestionTask"]
