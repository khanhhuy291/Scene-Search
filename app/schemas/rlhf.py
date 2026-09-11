"""Pydantic schemas for RLHF ranking feedback and Reranker dataset export."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RankedSceneItem(BaseModel):
    """A scene item within an original or reordered ranking."""

    model_config = ConfigDict(str_strip_whitespace=True)

    scene_id: str = Field(..., description="Unique ID of the scene/point")
    video_id: str | None = Field(default=None, description="Video UUID or identifier")
    timestamp_s: float | None = Field(default=None, description="Timestamp in seconds")
    score: float | None = Field(default=None, description="Similarity or relevance score")
    rank: int = Field(..., ge=1, description="Rank position (1-indexed)")
    caption: str | None = Field(default=None, description="Scene caption or summary")
    preview_url: str | None = Field(default=None, description="Thumbnail or preview URL")


class RLHFFeedbackCreate(BaseModel):
    """Payload submitted when an engineer/annotator submits reordered top-k results."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=2000, description="Search query")
    mode: str = Field(default="qwen", description="Search mode used")
    original_ranking: list[RankedSceneItem] = Field(
        ..., min_length=1, description="Original list of scenes from search"
    )
    reordered_ranking: list[RankedSceneItem] = Field(
        ..., min_length=1, description="Human-preferred reordered list of scenes"
    )
    notes: str | None = Field(
        default=None, max_length=2000, description="Optional annotation notes"
    )


class RLHFFeedbackResponse(BaseModel):
    """Feedback record returned to client or admin dashboard."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID
    query: str
    mode: str
    original_ranking: list[dict[str, Any]]
    reordered_ranking: list[dict[str, Any]]
    notes: str | None = None
    user_id: UUID | None = None
    user_email: str | None = None
    created_at: datetime
    updated_at: datetime


class RLHFFeedbackPage(BaseModel):
    """Paginated list of RLHF feedback entries."""

    model_config = ConfigDict(str_strip_whitespace=True)

    items: list[RLHFFeedbackResponse]
    total: int
    limit: int
    offset: int


class RLHFStatsResponse(BaseModel):
    """High-level summary of collected RLHF feedback dataset."""

    model_config = ConfigDict(str_strip_whitespace=True)

    total_submissions: int
    total_unique_queries: int
    total_reordered_items: int
    total_pairwise_preferences: int


class PairwisePreferenceItem(BaseModel):
    """Pairwise preference pair for Cross-Encoder / RankNet / DPO training."""

    query: str
    positive_scene_id: str
    negative_scene_id: str
    positive_rank: int
    negative_rank: int
    video_id: str | None = None
    timestamp_s: float | None = None
    caption: str | None = None


class ListwiseRankingItem(BaseModel):
    """Listwise ranking instance for LambdaMART / ListNet training."""

    query: str
    ranked_scenes: list[dict[str, Any]]
    annotator: str | None = None
    created_at: str
