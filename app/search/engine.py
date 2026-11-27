"""Query embeddings against Qdrant: SigLIP, Qwen, or both with RRF.

Only explicit payload filters constrain retrieval. Query text is embedded as
written; captions are display metadata, never a second retrieval path.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from core.config import get_settings
from ml.encoder import get_qwen_encoder, get_siglip_encoder
from schemas.search import Granularity, SearchFilters, SearchMode
from search.catalog import Keyframe, keyframe_from_payload
from search.cursor import Cursor, decode_cursor, fingerprint
from search.fusion import RankedList, reciprocal_rank_fusion
from search.query import ParsedQuery

CANDIDATE_LIMIT = 1500


@dataclass(frozen=True)
class VideoMatch:
    """Best vector match per video, plus other moments in the candidate pool."""

    keyframe: Keyframe
    score: float
    keyframes_matched: int
    signals: dict[str, float] = field(default_factory=dict)
    matched_keyframes: tuple[Keyframe, ...] = ()
    # Compatibility metadata; vector retrieval does not infer concepts or scan
    # the corpus to count all keyframes in a video.
    confirmed: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    keyframes_in_video: int = 0
    contradicting_moments: int = 0


@dataclass(frozen=True)
class SearchOutcome:
    parsed: ParsedQuery
    matches: tuple[VideoMatch, ...]
    total_videos: int
    total_keyframes: int
    exhaustive: bool
    signals_used: tuple[str, ...]
    next_cursor: str | None
    took_ms: float
    similarity_floor: float = 0.0
    below_threshold: bool = False
    model_version: str = ""
    # Compatibility fields for saved sessions and older API consumers.
    unconfirmed_concepts: tuple[str, ...] = ()
    degraded: bool = False


class SceneSearchEngine:
    """Retrieve a bounded candidate pool and present its best moment per video."""

    def __init__(
        self,
        *,
        client: Any = None,
        encoder: Any = None,
        encoders: dict[str, Any] | None = None,
        collection: str | None = None,
    ):
        self._client = client
        self._encoder = encoder
        self._encoders = encoders or {}
        self._collection = collection

    def _qdrant(self) -> Any:
        if self._client is not None:
            return self._client
        from infrastructure.qdrant import get_qdrant_client

        return get_qdrant_client()

    async def search(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        mode: SearchMode | None = None,
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
        video_ids: list[str] | None = None,
        min_score: float = 0.0,
        explain: bool = False,
    ) -> SearchOutcome:
        started = time.perf_counter()
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        mode = mode or get_settings().search.mode
        if mode not in ("siglip", "qwen", "hybrid"):
            raise ValueError("mode must be siglip, qwen, or hybrid (SigLIP + Qwen + RRF)")
        filters = filters or SearchFilters()
        if video_ids is not None:
            filters = filters.model_copy(update={"video_ids": video_ids})
        collection = self._collection or get_settings().qdrant.collection
        expected = fingerprint(
            query,
            {
                "version": "vector-only-v1",
                "mode": mode,
                "collection": collection,
                "filters": filters.model_dump(exclude_none=True),
                "min_score": min_score,
                "limit": limit,
                "pool": CANDIDATE_LIMIT,
            },
            granularity=granularity or "any",
        )
        decoded = decode_cursor(cursor, expected_fingerprint=expected) if cursor else None
        names = ("siglip", "qwen") if mode == "hybrid" else (mode,)
        client = self._qdrant()
        condition = self._filter(filters, granularity)

        versions: dict[str, str] = {}

        async def retrieve(name: str) -> list[Any]:
            encoder = self._encoders.get(name)
            if encoder is None:
                encoder = self._encoder
            if encoder is None:
                encoder = get_siglip_encoder() if name == "siglip" else get_qwen_encoder()
            versions[name] = getattr(encoder, "model_version", name)
            encoded = await asyncio.to_thread(encoder.encode_texts, [query])
            kwargs = dict(
                collection_name=collection,
                query=list(encoded[0]),
                using=name,
                limit=CANDIDATE_LIMIT,
                with_payload=True,
                query_filter=condition,
            )
            if min_score > 0:
                kwargs["score_threshold"] = min_score
            response = await client.query_points(**kwargs)
            return response.points

        # Both requested towers must succeed. Never silently substitute a mode.
        responses = await asyncio.gather(*(retrieve(name) for name in names))
        frames: dict[str, Keyframe] = {}
        for points in responses:
            for point in points:
                frame = keyframe_from_payload(str(point.id), point.payload or {})
                if frame is not None:
                    frames[frame.point_id] = frame
        if mode == "hybrid":
            ranked = reciprocal_rank_fusion(
                [
                    RankedList(signal=name, ids=[str(point.id) for point in points])
                    for name, points in zip(names, responses, strict=True)
                ]
            )
            scores = [(item.id, item.score, item.contributions) for item in ranked]
        else:
            scores = [
                (str(point.id), float(point.score), {mode: float(point.score)})
                for point in responses[0]
            ]
            scores.sort(key=lambda item: (-item[1], item[0]))
        moments: dict[str, list[Keyframe]] = {}
        for frame in frames.values():
            moments.setdefault(frame.video_id, []).append(frame)
        best: dict[str, VideoMatch] = {}
        for pid, score, contributions in scores:
            frame = frames.get(pid)
            if frame is None or frame.video_id in best:
                continue
            matched = sorted(moments[frame.video_id], key=lambda f: (f.timestamp_s, f.point_id))
            best[frame.video_id] = VideoMatch(
                keyframe=frame,
                score=score,
                keyframes_matched=len(matched),
                matched_keyframes=tuple(matched),
                signals=contributions if explain else {},
            )
        grouped = sorted(best.values(), key=lambda m: (-m.score, m.keyframe.point_id))
        remaining = grouped
        if decoded:
            remaining = [
                m
                for m in grouped
                if m.score < decoded.last_score
                or (m.score == decoded.last_score and m.keyframe.point_id > decoded.last_id)
            ]
        page = remaining[:limit]
        next_token = None
        if len(remaining) > limit:
            last = page[-1]
            next_token = Cursor(
                fingerprint=expected,
                last_score=last.score,
                last_id=last.keyframe.point_id,
                offset=(decoded.offset if decoded else 0) + len(page),
            ).encode()
        return SearchOutcome(
            parsed=ParsedQuery(raw=query, semantic_text=query),
            matches=tuple(page),
            total_videos=len(grouped),
            total_keyframes=len(frames),
            exhaustive=False,
            signals_used=(*names, "rrf") if mode == "hybrid" else names,
            next_cursor=next_token,
            took_ms=(time.perf_counter() - started) * 1000,
            model_version=" + ".join(versions[name] for name in names),
            similarity_floor=min_score,
            below_threshold=min_score > 0 and not any(responses),
        )

    @staticmethod
    def _filter(filters: SearchFilters, granularity: Granularity | None) -> Any:
        from qdrant_client.http import models

        from search.points import build_filter

        values = filters.model_dump(exclude={"min_object_counts"})
        condition = build_filter(**values, granularity=granularity)
        counts = filters.min_object_counts or {}
        if counts:
            condition = condition or models.Filter(must=[])
            condition.must = list(condition.must or []) + [
                models.FieldCondition(key=f"object_counts.{name}", range=models.Range(gte=count))
                for name, count in counts.items()
            ]
        return condition


_engine: SceneSearchEngine | None = None


def get_search_engine() -> SceneSearchEngine:
    global _engine
    if _engine is None:
        _engine = SceneSearchEngine()
    return _engine


def reset_search_engine() -> None:
    global _engine
    _engine = None
