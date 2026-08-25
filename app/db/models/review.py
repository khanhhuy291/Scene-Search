"""Roles, review sessions, and dataset exports.

Implements the human-in-the-loop constraint: a dataset may only be exported from
an approved review session. The rule is enforced by a database constraint as well
as in the service layer, so it cannot be bypassed by a future API caller that
skips the UI (plan section 6.2).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    ENGINEER = "engineer"
    ADMIN = "admin"


class SessionStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class Verdict(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    UNSURE = "unsure"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    __table_args__ = (
        CheckConstraint(
            "role IN ('engineer', 'admin')",
            name="role_allowed",
        ),
    )


class ReviewSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved search plus the engineer's relevance judgements on its results."""

    __tablename__ = "review_sessions"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    # Retained for provenance: an exported dataset must be reproducible from the
    # query and filters that produced it.
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")

    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    decisions: Mapped[list[ReviewDecision]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    datasets: Mapped[list[Dataset]] = relationship(back_populates="session")

    __table_args__ = (
        Index("ix_review_sessions_status", "status"),
        Index("ix_review_sessions_created_by", "created_by"),
        # Target of the composite foreign key from ``datasets``; see the
        # explanation on Dataset.__table_args__.
        UniqueConstraint("id", "status", name="uq_review_sessions_id_status"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'rejected')",
            name="status_allowed",
        ),
        # An approval is meaningless without a recorded approver and timestamp.
        CheckConstraint(
            "(status <> 'approved') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="approved_requires_approver",
        ),
        # Self-approval would defeat the purpose of the review gate.
        CheckConstraint(
            "approved_by IS NULL OR approved_by <> created_by",
            name="approver_differs_from_author",
        ),
    )


class ReviewDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One engineer verdict on one frame within a session."""

    __tablename__ = "review_decisions"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False
    )
    frame_id: Mapped[UUID] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    session: Mapped[ReviewSession] = relationship(back_populates="decisions")

    __table_args__ = (
        UniqueConstraint("session_id", "frame_id", name="uq_review_decisions_session_id_frame_id"),
        Index("ix_review_decisions_verdict", "verdict"),
        CheckConstraint(
            "verdict IN ('relevant', 'irrelevant', 'unsure')",
            name="verdict_allowed",
        ),
    )


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An exported dataset or test set, always traceable to an approved session."""

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[UUID] = mapped_column(nullable=False)
    # Denormalized so the composite foreign key below can pin it to 'approved'.
    # Never set by hand: the export service copies the session status, and the
    # constraint pair rejects anything other than an approved source.
    session_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="approved"
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False, server_default="jsonl")
    manifest_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Frozen copy of the query, filters, model version, and approver, so the
    # export stays interpretable even if the session is later modified.
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    exported_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[ReviewSession] = relationship(back_populates="datasets")

    # The human-in-the-loop guarantee, enforced by the database rather than by
    # application code alone.
    #
    # A CHECK constraint cannot read another table, so the session status is
    # denormalized here and pinned to 'approved', while a composite foreign key
    # ties (session_id, session_status) to the matching pair in review_sessions.
    # Together these make an export from a draft, submitted, or rejected session
    # unrepresentable. ON UPDATE RESTRICT additionally prevents un-approving a
    # session that has already been exported, which would otherwise leave a
    # dataset whose stated provenance is no longer true.
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "session_status"],
            ["review_sessions.id", "review_sessions.status"],
            name="fk_datasets_session_id_session_status_review_sessions",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        Index("ix_datasets_session_id", "session_id"),
        CheckConstraint("item_count >= 0", name="item_count_non_negative"),
        CheckConstraint("session_status = 'approved'", name="source_session_approved"),
        CheckConstraint(
            "format IN ('jsonl', 'coco', 'parquet')",
            name="format_allowed",
        ),
    )


__all__ = [
    "Dataset",
    "ReviewDecision",
    "ReviewSession",
    "SessionStatus",
    "User",
    "UserRole",
    "Verdict",
]
