"""RLHF and Reranker fine-tuning human feedback model."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RLHFFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Human feedback on search result rankings (used to fine-tune rerankers)."""

    __tablename__ = "rlhf_feedback"

    query: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="qwen")
    # List of [{scene_id, video_id, timestamp_s, score, rank, caption}, ...] in initial retrieval order
    original_ranking: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    # List of [{scene_id, video_id, timestamp_s, rank, user_rank}, ...] in human-preferred order
    reordered_ranking: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    __table_args__ = (
        Index("ix_rlhf_feedback_created_at", "created_at"),
        Index("ix_rlhf_feedback_query", "query"),
    )


__all__ = ["RLHFFeedback"]
