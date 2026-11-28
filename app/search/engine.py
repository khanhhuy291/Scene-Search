"""Five explicit vector searches over the new ingestion representation.

Queries are embedded as typed. Caption search uses Qwen text embeddings against
stored caption vectors, without caption generation, lexical search or query rules.
Only published ingestion runs and explicit payload filters constrain candidates.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import models

from core.config import get_settings
from ml.encoder import get_qwen_encoder, get_siglip_encoder
from ml.vectors import normalize_vectors
from repositories.scene_graph import active_publications
from schemas.search import Granularity, SearchFilters, SearchMode
from search.catalog import Keyframe, keyframe_from_payload
from search.cursor import Cursor, CursorError, decode_cursor, fingerprint
from search.fusion import RankedList, reciprocal_rank_fusion
from search.publication import publication_filter
from search.query import ParsedQuery

MODE_VECTORS = {
    "siglip": ("siglip",),
    "qwen": ("qwen",),
    "caption": ("caption",),
    "siglip_qwen_rrf": ("siglip", "qwen"),
    "qwen_caption_rrf": ("qwen", "caption"),
}
CANDIDATE_LIMIT = 1500


@dataclass(frozen=True)
class VideoMatch:
    """One video's best admissible keyframe."""

    keyframe: Keyframe
    score: float
    keyframes_matched: int
    confirmed: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    signals: dict[str, float] = field(default_factory=dict)
    keyframes_in_video: int = 0
    contradicting_moments: int = 0
    matched_keyframes: tuple[Keyframe, ...] = ()


@dataclass(frozen=True)
class SearchOutcome:
    """Everything the API layer needs to build a response."""

    parsed: ParsedQuery
    matches: tuple[VideoMatch, ...]
    total_videos: int
    total_keyframes: int
    exhaustive: bool
    signals_used: tuple[str, ...]
    next_cursor: str | None
    took_ms: float

    model_version: str = ""
    similarity_floor: float = 0.0
    below_threshold: bool = False
    unconfirmed_concepts: tuple[str, ...] = ()

    degraded: bool = False


class PublicationChangedError(RuntimeError):
    """Ingestion or caption replacement changed results during retrieval."""


class SceneSearchEngine:
    def __init__(
        self,
        *,
        client: Any = None,
        encoder: Any = None,
        caption_encoder: Any = None,
        encoders: dict[str, Any] | None = None,
    ):
        self._client = client
        self._encoder = encoder
        self._caption_encoder = caption_encoder
        self._encoders = encoders or {}

    def _qdrant(self):
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
        query = query.strip()
        if not query or not 1 <= limit <= 100 or not 0 <= min_score <= 1:
            raise ValueError("Invalid query, limit or minimum cosine score")
        mode = mode or get_settings().search.mode
        if mode not in MODE_VECTORS:
            raise ValueError("Unsupported vector search mode")
        # Qwen and caption vectors exist on chunks, not on the keyframe index.
        if granularity == "frame" and mode != "siglip":
            raise ValueError("Frame retrieval supports SigLIP only; use segments for this mode")
        for attempt in range(2):
            try:
                return await self._retrieve(
                    query,
                    limit=limit,
                    cursor=cursor,
                    mode=mode,
                    filters=filters or SearchFilters(),
                    granularity=granularity or "segment",
                    video_ids=video_ids,
                    min_score=min_score,
                    explain=explain,
                )
            except PublicationChangedError:
                if cursor:
                    raise CursorError("Publication changed; restart search from the first page")
                if attempt:
                    raise
        raise RuntimeError("Unable to pin the active ingestion publication")

    async def _retrieve(
        self, query, *, limit, cursor, mode, filters, granularity, video_ids, min_score, explain
    ):
        started = time.perf_counter()
        settings = get_settings()
        scope = set(video_ids) if video_ids is not None else None
        if filters.video_ids:
            scope = set(filters.video_ids) if scope is None else scope & set(filters.video_ids)
        publications = await active_publications(scope)
        collection = (
            settings.qdrant.keyframe_collection
            if granularity == "frame"
            else settings.qdrant.chunk_collection
        )
        names = MODE_VECTORS[mode]
        parsed = ParsedQuery(raw=query, semantic_text=query)
        if not publications:
            if cursor:
                raise CursorError("Publication changed; restart search from the first page")
            return SearchOutcome(
                parsed,
                (),
                0,
                0,
                False,
                (),
                None,
                (time.perf_counter() - started) * 1000,
                model_version="not_queried",
                similarity_floor=min_score,
            )
        client = self._qdrant()
        # Share one Qwen text embedding between Qwen-image and caption retrieval.
        encoders = {}
        for name in names:
            tower = "siglip" if name == "siglip" else "qwen"
            if tower not in encoders:
                enc = self._encoders.get(tower)
                if enc is None:
                    enc = self._encoder if tower == "siglip" else self._caption_encoder
                if enc is None:
                    enc = get_siglip_encoder() if tower == "siglip" else get_qwen_encoder()
                encoders[tower] = enc

        async def encode(tower, encoder):
            vector = await asyncio.to_thread(encoder.encode_texts, [query])
            return tower, normalize_vectors(vector, dimension=encoder.dimension, count=1)[0]

        encoded = dict(await asyncio.gather(*(encode(k, v) for k, v in encoders.items())))
        versions = {
            name: encoders["siglip" if name == "siglip" else "qwen"].model_version for name in names
        }
        expected_base = {
            "version": "published-vector-search-v1",
            "mode": mode,
            "collection": collection,
            "publications": publications,
            "models": versions,
            "limit": limit,
            "filters": filters.model_dump(exclude_none=True),
            "video_ids": sorted(scope or []),
            "min_score": min_score,
            "pool": CANDIDATE_LIMIT,
        }

        async def ann(name):
            condition = self._filter(filters, granularity)
            condition.must = list(condition.must or []) + [
                publication_filter(publications),
                models.FieldCondition(
                    key="privacy_status", match=models.MatchValue(value="verified")
                ),
                models.FieldCondition(
                    key="model_version" if granularity == "frame" else f"{name}_embedding_version",
                    match=models.MatchValue(value=versions[name]),
                ),
            ]
            if name == "caption":
                condition.must.append(
                    models.FieldCondition(
                        key="caption_embedding_status", match=models.MatchValue(value="ready")
                    )
                )
            kwargs = dict(
                collection_name=collection,
                using=name,
                query=encoded["siglip" if name == "siglip" else "qwen"],
                query_filter=condition,
                limit=CANDIDATE_LIMIT,
                with_payload=True,
            )
            if min_score > 0:
                kwargs["score_threshold"] = min_score
            response = await client.query_points(**kwargs)
            return response.points

        # Failure of a selected tower fails the request; never switch modes silently.
        responses = await asyncio.gather(*(ann(name) for name in names))
        records, frames = {}, {}
        for points in responses:
            for point in points:
                identifier = str(point.id)
                payload = point.payload or {}
                if publications.get(payload.get("video_id")) != payload.get("ingestion_run_id"):
                    raise PublicationChangedError("Retrieved a different publication")
                if identifier in records and records[identifier] != payload:
                    raise PublicationChangedError("Chunk changed between vector searches")
                records[identifier] = payload
                frame = keyframe_from_payload(identifier, payload)
                if frame is not None:
                    frames[identifier] = frame
        if len(names) == 2:
            fused = reciprocal_rank_fusion(
                [
                    RankedList(name, [str(p.id) for p in points])
                    for name, points in zip(names, responses, strict=True)
                ]
            )
            scores = [(item.id, item.score, item.contributions) for item in fused]
        else:
            scores = [(str(p.id), float(p.score), {names[0]: float(p.score)}) for p in responses[0]]
            scores.sort(key=lambda item: (-item[1], item[0]))
        grouped = {}
        moments = {}
        for frame in frames.values():
            moments.setdefault(frame.video_id, []).append(frame)
        for identifier, score, contributions in scores:
            frame = frames.get(identifier)
            if frame is None or frame.video_id in grouped:
                continue
            matched = sorted(moments[frame.video_id], key=lambda f: (f.timestamp_s, f.point_id))
            grouped[frame.video_id] = VideoMatch(
                frame,
                score,
                len(matched),
                signals=contributions if explain else {},
                matched_keyframes=tuple(matched),
            )
        ranked = sorted(grouped.values(), key=lambda m: (-m.score, m.keyframe.point_id))
        expected = fingerprint(
            query,
            {**expected_base, "ranking": [(m.keyframe.point_id, m.score) for m in ranked]},
            granularity=granularity,
        )
        decoded = decode_cursor(cursor, expected_fingerprint=expected) if cursor else None
        remaining = (
            ranked
            if decoded is None
            else [
                m
                for m in ranked
                if m.score < decoded.last_score
                or (m.score == decoded.last_score and m.keyframe.point_id > decoded.last_id)
            ]
        )
        page = remaining[:limit]
        token = None
        if len(remaining) > limit:
            last = page[-1]
            token = Cursor(
                expected,
                last.score,
                last.keyframe.point_id,
                (decoded.offset if decoded else 0) + len(page),
            ).encode()
        # Keep the new ingestion publication guarantee without a corpus caption scan.
        selected = {f.point_id for match in page for f in match.matched_keyframes}
        for start in range(0, len(selected), 256):
            ids = sorted(selected)[start : start + 256]
            fresh = await client.retrieve(
                collection_name=collection, ids=ids, with_payload=True, with_vectors=False
            )
            if {str(p.id) for p in fresh} != set(ids) or any(
                p.payload != records[str(p.id)] for p in fresh
            ):
                raise PublicationChangedError("Result metadata changed during retrieval")
        if await active_publications(scope) != publications:
            raise PublicationChangedError("Ingestion publication changed during retrieval")
        return SearchOutcome(
            parsed,
            tuple(page),
            len(ranked),
            len(frames),
            False,
            (*names, "rrf") if len(names) == 2 else names,
            token,
            (time.perf_counter() - started) * 1000,
            model_version=" + ".join(f"{name}:{versions[name]}" for name in names),
            similarity_floor=min_score,
            below_threshold=min_score > 0 and not any(responses),
        )

    @staticmethod
    def _filter(filters: SearchFilters, granularity: Granularity):
        from search.points import build_filter

        condition = build_filter(
            **filters.model_dump(exclude={"min_object_counts"}), granularity=granularity
        ) or models.Filter(must=[])
        condition.must = list(condition.must or []) + [
            models.FieldCondition(key=f"object_counts.{name}", range=models.Range(gte=count))
            for name, count in (filters.min_object_counts or {}).items()
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
