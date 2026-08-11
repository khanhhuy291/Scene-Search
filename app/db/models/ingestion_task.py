"""Database model for ingestion task status."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class IngestionTask(Base):
    """Durable status and result metadata for one ingestion task."""

    __tablename__ = "ingestion_tasks"
    __table_args__ = (
        CheckConstraint(
            "progress BETWEEN 0 AND 100",
            name="ck_ingestion_tasks_progress_range",
        ),
    )

    task_id: Mapped[UUID] = mapped_column(primary_key=True)
    video_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
