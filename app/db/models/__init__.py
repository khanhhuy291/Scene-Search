"""SQLAlchemy models.

Importing every model here keeps ``Base.metadata`` complete, which is what
Alembic autogenerate inspects.
"""

from db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from db.models.corpus import (
    BehaviorEvent,
    Frame,
    FrameAttribute,
    FrameObject,
    Segment,
    Video,
)
from db.models.ingestion_task import IngestionTask
from db.models.review import (
    Dataset,
    ReviewDecision,
    ReviewSession,
    SessionStatus,
    User,
    UserRole,
    Verdict,
)

__all__ = [
    "Base",
    "BehaviorEvent",
    "Dataset",
    "Frame",
    "FrameAttribute",
    "FrameObject",
    "IngestionTask",
    "ReviewDecision",
    "ReviewSession",
    "Segment",
    "SessionStatus",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserRole",
    "Verdict",
    "Video",
]
