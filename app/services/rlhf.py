"""RLHF human feedback service for search reranking and dataset curation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger
from sqlalchemy import func, select

from db.models.review import User
from db.models.rlhf import RLHFFeedback
from infrastructure.postgres import get_session_factory
from schemas.rlhf import (
    ListwiseRankingItem,
    PairwisePreferenceItem,
    RLHFFeedbackCreate,
    RLHFFeedbackPage,
    RLHFFeedbackResponse,
    RLHFStatsResponse,
)


async def save_rlhf_feedback(
    payload: RLHFFeedbackCreate,
    user: User | None = None,
) -> RLHFFeedbackResponse:
    """Store a human reordering / ranking feedback record into PostgreSQL."""
    now = datetime.now(UTC)
    feedback_id = uuid4()

    record = RLHFFeedback(
        id=feedback_id,
        query=payload.query.strip(),
        mode=payload.mode,
        original_ranking=[item.model_dump() for item in payload.original_ranking],
        reordered_ranking=[item.model_dump() for item in payload.reordered_ranking],
        notes=payload.notes,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        created_at=now,
        updated_at=now,
    )

    factory = get_session_factory()
    async with factory() as session:
        session.add(record)
        await session.commit()

    logger.info(
        "Recorded RLHF ranking feedback for query='{}', {} items reordered by user={}",
        payload.query,
        len(payload.reordered_ranking),
        user.email if user else "anonymous",
    )

    return RLHFFeedbackResponse(
        id=record.id,
        query=record.query,
        mode=record.mode,
        original_ranking=record.original_ranking,
        reordered_ranking=record.reordered_ranking,
        notes=record.notes,
        user_id=record.user_id,
        user_email=record.user_email,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def list_rlhf_feedback(
    *,
    limit: int = 25,
    offset: int = 0,
    query_filter: str | None = None,
) -> RLHFFeedbackPage:
    """List paginated RLHF feedback records with optional query filtering."""
    factory = get_session_factory()
    async with factory() as session:
        base_query = select(RLHFFeedback)
        count_query = select(func.count(RLHFFeedback.id))

        if query_filter:
            term = f"%{query_filter.strip()}%"
            base_query = base_query.where(RLHFFeedback.query.ilike(term))
            count_query = count_query.where(RLHFFeedback.query.ilike(term))

        total = (await session.scalar(count_query)) or 0

        statement = base_query.order_by(RLHFFeedback.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.scalars(statement)).all()

        items = [
            RLHFFeedbackResponse(
                id=row.id,
                query=row.query,
                mode=row.mode,
                original_ranking=row.original_ranking,
                reordered_ranking=row.reordered_ranking,
                notes=row.notes,
                user_id=row.user_id,
                user_email=row.user_email,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    return RLHFFeedbackPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_rlhf_stats() -> RLHFStatsResponse:
    """Compute aggregate dataset statistics for RLHF submissions."""
    factory = get_session_factory()
    async with factory() as session:
        total_submissions = (await session.scalar(select(func.count(RLHFFeedback.id)))) or 0
        total_unique_queries = (
            await session.scalar(select(func.count(func.distinct(RLHFFeedback.query))))
        ) or 0

        rows = (await session.scalars(select(RLHFFeedback.reordered_ranking))).all()
        total_items = sum(len(r) for r in rows if isinstance(r, list))

        # Number of pairwise combinations: n * (n - 1) / 2 for each list
        total_pairs = sum(
            (len(r) * (len(r) - 1)) // 2 for r in rows if isinstance(r, list) and len(r) > 1
        )

    return RLHFStatsResponse(
        total_submissions=total_submissions,
        total_unique_queries=total_unique_queries,
        total_reordered_items=total_items,
        total_pairwise_preferences=total_pairs,
    )


async def export_rlhf_dataset(format_type: str = "jsonl") -> str:
    """Export the collected human feedback into JSONL for model training.

    Supported formats:
    - 'pairwise': Pairwise preference pairs (query, positive_scene, negative_scene) for Cross-Encoder/RankNet.
    - 'listwise': Full ranked lists (query, ordered_scenes) for LambdaMART/ListNet/Qwen Reranker.
    - 'jsonl' / 'raw': Complete feedback records with original and user rankings.
    """
    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.scalars(select(RLHFFeedback).order_by(RLHFFeedback.created_at.asc()))
        ).all()

    output_lines: list[str] = []

    if format_type == "pairwise":
        for record in rows:
            reordered = record.reordered_ranking or []
            # Each pair where item_i is ranked strictly ahead of item_j
            for i in range(len(reordered)):
                for j in range(i + 1, len(reordered)):
                    pos = reordered[i]
                    neg = reordered[j]
                    pair = PairwisePreferenceItem(
                        query=record.query,
                        positive_scene_id=str(pos.get("scene_id", "")),
                        negative_scene_id=str(neg.get("scene_id", "")),
                        positive_rank=i + 1,
                        negative_rank=j + 1,
                        video_id=pos.get("video_id"),
                        timestamp_s=pos.get("timestamp_s"),
                        caption=pos.get("caption"),
                    )
                    output_lines.append(json.dumps(pair.model_dump(), ensure_ascii=False))

    elif format_type == "listwise":
        for record in rows:
            item = ListwiseRankingItem(
                query=record.query,
                ranked_scenes=record.reordered_ranking or [],
                annotator=record.user_email,
                created_at=record.created_at.isoformat(),
            )
            output_lines.append(json.dumps(item.model_dump(), ensure_ascii=False))

    else:
        for record in rows:
            doc = {
                "id": str(record.id),
                "query": record.query,
                "mode": record.mode,
                "original_ranking": record.original_ranking,
                "reordered_ranking": record.reordered_ranking,
                "notes": record.notes,
                "user_email": record.user_email,
                "created_at": record.created_at.isoformat(),
            }
            output_lines.append(json.dumps(doc, ensure_ascii=False))

    return "\n".join(output_lines)
