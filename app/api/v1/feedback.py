"""RLHF Reranking Feedback and Dataset Curation API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse

from api.deps import get_current_user_optional, require_admin
from db.models.review import User
from schemas.rlhf import (
    RLHFFeedbackCreate,
    RLHFFeedbackPage,
    RLHFFeedbackResponse,
    RLHFStatsResponse,
)
from services.rlhf import (
    export_rlhf_dataset,
    get_rlhf_stats,
    list_rlhf_feedback,
    save_rlhf_feedback,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "/rerank",
    response_model=RLHFFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit human reordering/reranking feedback on top-k search results",
)
async def submit_rerank_feedback(
    payload: RLHFFeedbackCreate,
    user: Annotated[User | None, Depends(get_current_user_optional)] = None,
) -> RLHFFeedbackResponse:
    """Record human preference re-ranking of top-k search results for RLHF/Reranker training."""
    return await save_rlhf_feedback(payload, user=user)


@router.get(
    "/rerank",
    response_model=RLHFFeedbackPage,
    summary="List all RLHF feedback submissions (Admin only)",
)
async def list_feedback(
    _: Annotated[User, Depends(require_admin)],
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, description="Filter by query text"),
) -> RLHFFeedbackPage:
    """Retrieve paginated search feedback submissions."""
    return await list_rlhf_feedback(limit=limit, offset=offset, query_filter=q)


@router.get(
    "/stats",
    response_model=RLHFStatsResponse,
    summary="Get summary metrics on collected RLHF feedback dataset (Admin only)",
)
async def get_stats(
    _: Annotated[User, Depends(require_admin)],
) -> RLHFStatsResponse:
    """Aggregate statistics on total feedback submissions and preference pairs."""
    return await get_rlhf_stats()


@router.get(
    "/export",
    response_class=PlainTextResponse,
    summary="Export RLHF dataset for Cross-Encoder / Qwen Reranker fine-tuning (Admin only)",
)
async def export_dataset(
    _: Annotated[User, Depends(require_admin)],
    format: str = Query(
        default="jsonl",
        pattern="^(jsonl|pairwise|listwise)$",
        description="Dataset export format: 'jsonl', 'pairwise', or 'listwise'",
    ),
) -> PlainTextResponse:
    """Generate training dataset in JSONL format."""
    content = await export_rlhf_dataset(format_type=format)
    filename = f"rlhf_reranker_{format}.jsonl"
    return PlainTextResponse(
        content=content,
        media_type="application/x-jsonlines",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
