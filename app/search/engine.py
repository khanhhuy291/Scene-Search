"""Chunk and keyframe retrieval over the active publication."""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from loguru import logger
from qdrant_client import models

from core.config import get_settings
from ml.encoder import get_qwen_encoder, get_siglip_encoder
from ml.vectors import normalize_vectors
from pipelines.ingestion.scene_metadata import aggregate_observations, metadata_payload
from repositories.scene_graph import active_publications
from schemas.search import Granularity, SearchFilters
from search.catalog import (
    Keyframe,
    keyframe_from_payload,
)
from search.cursor import Cursor, apply_cursor, decode_cursor, fingerprint
from search.fusion import RankedList, reciprocal_rank_fusion
from search.publication import PublishedChunkCatalog, publication_filter
from search.query import (
    ParsedQuery,
    evaluate_caption,
    parse_query,
)
from search.verification import verify_chunk

SearchMode = Literal["hybrid", "visual", "caption", "qwen", "siglip"]
MAX_POOL = 6000


def _qwen_is_ready(encoder: Any) -> bool:
    """True when the Qwen tower can encode without pulling a 2B checkpoint.

    Hybrid search must not download or load Qwen3-VL-Embedding-2B on the request
    path: that blocks the event loop and can OOM a process that already holds
    SigLIP. A remote endpoint, or weights already resident in this process, is
    the only case where the tower is used.
    """

    client = getattr(encoder, "client", encoder)
    settings = getattr(client, "settings", None)
    if getattr(settings, "qwen_embedding_url", ""):
        return True
    has_st = getattr(client, "_st_model", None) is not None
    has_model = getattr(client, "_model", None) is not None
    return has_st or has_model


@dataclass(frozen=True)
class VideoMatch:
    """One video's best admissible keyframe."""

    keyframe: Keyframe
    score: float
    # Admissible keyframes in this video, this one included. The UI reports it as
    # "N matching moments"; for the training-set use case it is the number that
    # says how much usable footage the clip actually contains.
    keyframes_matched: int
    # Concepts the caption positively confirmed, and excluded concepts it
    # explicitly reported as absent. Absence stated by the caption is stronger
    # evidence than silence and is worth surfacing.
    confirmed: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    # Per-signal fusion contributions, populated only when explain was requested.
    signals: dict[str, float] = field(default_factory=dict)
    # Every keyframe this video has in the index, matching or not. The
    # denominator that turns "3 moments" into "3 of 21 moments in this clip".
    keyframes_in_video: int = 0
    # Moments in this same clip whose caption positively shows something the
    # query excluded. Surfacing this is what stops a correct result from reading
    # as a bug when the user watches the rest of the clip and finds a pedestrian.
    contradicting_moments: int = 0
    # All admissible matching keyframes for this video.
    matched_keyframes: tuple[Keyframe, ...] = ()


@dataclass(frozen=True)
class SearchOutcome:
    """Everything the API layer needs to build a response."""

    parsed: ParsedQuery
    matches: tuple[VideoMatch, ...]
    total_videos: int
    total_keyframes: int
    # True when the caption scan could guarantee a complete answer set. False
    # means the results are the best of a large ranked pool -- good answers, but
    # not a promise that nothing was missed.
    exhaustive: bool
    signals_used: tuple[str, ...]
    next_cursor: str | None
    took_ms: float

    # The similarity floor that was in force, and whether it is the reason the
    # answer is empty. Together these separate "nothing in this corpus looks like
    # what you asked for" from "your filters excluded everything", which are the
    # two very different things an empty result can mean.
    similarity_floor: float = 0.0
    below_threshold: bool = False
    # Concepts the query required that no caption confirmed anywhere. The other
    # honest reason for an empty answer, and the actionable one: it names the word
    # to drop.
    unconfirmed_concepts: tuple[str, ...] = ()

    # A requested retrieval signal errored rather than returning nothing. Kept
    # separate from an empty result because the two look identical in the
    # response body and mean opposite things: "the corpus has nothing like this"
    # versus "we could not look".
    degraded: bool = False
    # Vector candidates the snapshot has never seen. Non-zero means the catalog
    # is behind the collection, which is direct evidence the caption scan could
    # not have been exhaustive.
    stale_candidates: int = 0
    # Per video, how many keyframes positively show a concept the query excluded.
    # A lower bound -- see ChunkCatalog.contradicting_positions.
    contradicting_moments: dict[str, int] = field(default_factory=dict)


def group_chunks(matches: list[VideoMatch], totals: Counter[str]) -> list[VideoMatch]:
    """Keep one video card and the best nonoverlapping matching chunks inside it."""
    grouped: dict[str, list[VideoMatch]] = {}
    for match in matches:
        grouped.setdefault(match.keyframe.video_id, []).append(match)
    result = []
    for video, candidates in grouped.items():
        moments, seen = [], set()
        for candidate in candidates:
            frame = candidate.keyframe
            verification = (frame.metadata or {}).get("search_verification", {})
            timestamps = tuple(verification.get("matching_timestamps_ms", []))
            identity = (
                frame.semantic_scene_id,
                frame.ingestion_run_id,
                timestamps or (frame.timestamp_s, frame.end_timestamp_s),
            )
            if identity in seen:
                continue
            seen.add(identity)
            moments.append(frame)
        best = candidates[0]
        result.append(
            replace(
                best,
                keyframes_matched=len(moments),
                keyframes_in_video=totals[video],
                matched_keyframes=tuple(sorted(moments, key=lambda f: (f.timestamp_s, f.point_id))),
            )
        )
    return sorted(result, key=lambda match: (-match.score, match.keyframe.point_id))


class PublicationChangedError(RuntimeError):
    """A request must restart with the newly published version."""


class SceneSearchEngine:
    """Retrieve, verify and rank published chunks before pagination."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        encoder: Any | None = None,
        caption_encoder: Any | None = None,
    ) -> None:
        self._client = client
        self._encoder = encoder
        self._caption_encoder = caption_encoder
        self._published_catalog = PublishedChunkCatalog()

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
        require: list[str] | None = None,
        exclude: list[str] | None = None,
        strict: bool | None = None,
        agentic: bool | None = None,
        rerank: bool | None = None,
    ) -> SearchOutcome:
        from core.tracer import get_tracer

        tracer = get_tracer()
        trace_ctx = tracer.create_context(query=query, trace_type="search")

        with trace_ctx.span("1. Phân tích cú pháp & Chuẩn hóa từ khóa", category="parser") as s:
            parsed = parse_query(query)
            if require is not None:
                parsed = replace(parsed, required=tuple(dict.fromkeys(require)))
            if exclude is not None:
                parsed = replace(parsed, excluded=tuple(dict.fromkeys(exclude)))
            s["required"] = list(parsed.required)
            s["excluded"] = list(parsed.excluded)
            s["embedding_text"] = parsed.embedding_text

        tuning = get_settings().search
        if mode is None:
            mode = tuning.mode
        use_agentic = (
            (tuning.agentic_enabled and self._client is None) if agentic is None else agentic
        )
        if not use_agentic:
            with trace_ctx.span(
                f"2. Truy xuất Vector & Lọc ({mode.upper()})", category="vectordb"
            ) as s:
                outcome = await self._execute_core_search(
                    query=query,
                    parsed=parsed,
                    limit=limit,
                    cursor=cursor,
                    mode=mode,
                    filters=filters,
                    granularity=granularity,
                    video_ids=video_ids,
                    min_score=min_score,
                    explain=explain,
                    strict=strict,
                    hyde_caption=None,
                    extra_signals=(),
                    rerank=rerank,
                )
                s["matches_found"] = len(outcome.matches)
                s["total_videos"] = outcome.total_videos
        else:
            from search.agent import get_agent_orchestrator

            orchestrator = get_agent_orchestrator()

            async def _executor(
                step_parsed: ParsedQuery,
                step_hyde: str | None,
                step_signals: list[str],
            ) -> SearchOutcome:
                with trace_ctx.span(
                    f"3. Quét Vector Qdrant ({mode.upper()})", category="vectordb"
                ) as s:
                    res = await self._execute_core_search(
                        query=query,
                        parsed=step_parsed,
                        limit=limit,
                        cursor=cursor,
                        mode=mode,
                        filters=filters,
                        granularity=granularity,
                        video_ids=video_ids,
                        min_score=min_score,
                        explain=explain,
                        strict=strict,
                        hyde_caption=step_hyde,
                        extra_signals=tuple(step_signals),
                        rerank=rerank,
                    )
                    s["matches_found"] = len(res.matches)
                    s["total_videos"] = res.total_videos
                    return res

            with trace_ctx.span("2. Agentic Router & Visual-HyDE (LLM)", category="llm") as s:
                outcome, trace_info = await orchestrator.execute(
                    raw_query=query,
                    parsed=parsed,
                    retrieval_executor=_executor,
                )
                s["route"] = trace_info.route.value
                s["domain"] = trace_info.domain_verdict.value
                s["reason"] = trace_info.route_reason
                s["hyde_caption"] = trace_info.hyde_caption

        trace_ctx.record_metric("matches_count", len(outcome.matches))
        trace_ctx.record_metric("total_videos", outcome.total_videos)
        trace_ctx.record_metric("signals_used", list(outcome.signals_used))
        trace_ctx.record_metric("took_ms", round(outcome.took_ms, 2))
        tracer.record(trace_ctx.finish(status="ok" if not outcome.degraded else "degraded"))

        return outcome

    async def _execute_core_search(
        self, query: str, parsed: ParsedQuery, **kwargs: Any
    ) -> SearchOutcome:
        for attempt in range(2):
            try:
                return await self._search_snapshot(query, parsed, **kwargs)
            except PublicationChangedError:
                self._published_catalog.invalidate()
                if attempt:
                    raise
        raise RuntimeError("Unable to pin the search publication")

    async def _frame_matches(
        self,
        candidates: list[VideoMatch],
        records: dict[str, Any],
        parsed: ParsedQuery,
        filters: SearchFilters | None,
        *,
        strict: bool,
    ) -> list[VideoMatch]:
        """Honor explicit frame requests without borrowing a chunk's evidence."""
        identifiers = list(
            {
                identifier
                for match in candidates
                for identifier in records[match.keyframe.point_id].payload["keyframe_ids"]
            }
        )
        points = {}
        for start in range(0, len(identifiers), 256):
            batch = await self._qdrant().retrieve(
                collection_name=get_settings().qdrant.keyframe_collection,
                ids=identifiers[start : start + 256],
                with_payload=True,
                with_vectors=False,
            )
            points.update((str(point.id), point) for point in batch)
        result = {}
        for match in candidates:
            parent = records[match.keyframe.point_id].payload
            for identifier in parent["keyframe_ids"]:
                point = points.get(identifier)
                if point is None:
                    continue
                data = point.payload
                if (
                    data.get("ingestion_run_id") != parent["ingestion_run_id"]
                    or data.get("video_id") != parent["video_id"]
                ):
                    continue
                timestamp = data["timestamp_ms"] / 1000
                if (
                    filters
                    and filters.time_range_s
                    and not filters.time_range_s[0] <= timestamp <= filters.time_range_s[1]
                ):
                    continue
                observation = next(
                    (
                        o
                        for o in match.keyframe.evidence.observations
                        if o.frame_index == data["frame_id"]
                        and o.timestamp_ms == data["timestamp_ms"]
                    ),
                    None,
                )
                if observation is None:
                    # An unobserved frame cannot inherit the chunk caption.
                    if parsed.has_concepts or (filters and filters.has_constraints):
                        continue
                    frame = keyframe_from_payload(
                        identifier,
                        {
                            **data,
                            "granularity": "frame",
                            "ts_start_s": timestamp,
                            "ts_end_s": timestamp,
                        },
                    )
                    verdict = evaluate_caption("", parsed)
                else:
                    evidence = aggregate_observations(
                        [observation],
                        sampled_count=1,
                        representative_frame_index=observation.frame_index,
                        representative_timestamp_ms=observation.timestamp_ms,
                    )
                    frame = keyframe_from_payload(
                        identifier,
                        {
                            **data,
                            **metadata_payload(evidence),
                            "granularity": "frame",
                            "ts_start_s": timestamp,
                            "ts_end_s": timestamp,
                            "video_key": parent["video_key"],
                            "dataset": parent["dataset"],
                            "representative_frame_index": observation.frame_index,
                            "representative_timestamp_ms": observation.timestamp_ms,
                        },
                    )
                    verdict = verify_chunk(frame, parsed, filters, strict=strict)
                if (
                    frame is not None
                    and verdict is not None
                    and (identifier not in result or match.score > result[identifier].score)
                ):
                    result[identifier] = replace(
                        match, keyframe=frame, confirmed=verdict.confirmed, denied=verdict.denied
                    )
        return sorted(result.values(), key=lambda match: (-match.score, match.keyframe.point_id))

    async def _search_snapshot(
        self,
        query: str,
        parsed: ParsedQuery,
        *,
        limit: int = 20,
        cursor: str | None = None,
        mode: SearchMode = "hybrid",
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
        video_ids: list[str] | None = None,
        min_score: float = 0.0,
        explain: bool = False,
        strict: bool | None = None,
        hyde_caption: str | None = None,
        extra_signals: tuple[str, ...] = (),
        rerank: bool | None = None,
    ) -> SearchOutcome:
        started = time.perf_counter()
        settings = get_settings()
        tuning = settings.search
        metrics = {}
        strict = tuning.strict_concepts if strict is None else strict
        use_rerank = tuning.rerank_enabled if rerank is None else rerank
        ids = set(video_ids) if video_ids is not None else None
        if filters and filters.video_ids:
            ids = set(filters.video_ids) if ids is None else ids & set(filters.video_ids)
        publications = await active_publications(ids)
        client = self._qdrant()
        snapshot = await self._published_catalog.load(client, publications)
        records = snapshot.points
        frames = {}
        for identifier, point in records.items():
            data = point.payload or {}
            if filters and filters.dataset and data.get("dataset") not in filters.dataset:
                continue
            if filters and filters.time_range_s:
                start, end = filters.time_range_s
                if data["ts_end_s"] < start or data["ts_start_s"] > end:
                    continue
            frame = snapshot.frames.get(identifier)
            if frame is not None:
                frames[identifier] = frame
        totals = Counter(point.payload["video_id"] for point in records.values())
        observed_concepts = {
            concept
            for frame in frames.values()
            if frame.evidence
            for concept in frame.evidence.present_concepts
        }
        verification_started = time.perf_counter()
        verdicts = {
            identifier: verify_chunk(frame, parsed, filters, strict=strict)
            for identifier, frame in frames.items()
        }
        frames = {
            identifier: frame
            for identifier, frame in frames.items()
            if verdicts[identifier] is not None
        }
        metrics["verification_duration_ms"] = (time.perf_counter() - verification_started) * 1000
        metrics["scoped_chunks"] = sum(1 for point in records.values())
        metrics["admissible_chunks"] = len(frames)
        rankings, signals = [], list(extra_signals)
        degraded = False
        vector_searches = 0
        vector_hits = False
        pool = min(MAX_POOL, max(1500, limit * 10))
        encoded: dict[tuple[int, int, str], list[float]] = {}

        async def ann(collection, name, signal, encoder, threshold, *, keyframes=False):
            nonlocal degraded, vector_searches, vector_hits
            source_started = time.perf_counter()
            try:
                dimension = encoder.dimension
                text = (
                    parsed.embedding_text
                    if name == "caption"
                    else hyde_caption or parsed.embedding_text
                )
                cache_key = (id(encoder), dimension, text)
                if cache_key not in encoded:
                    encoded[cache_key] = normalize_vectors(
                        await asyncio.to_thread(encoder.encode_texts, [text]),
                        dimension=dimension,
                        count=1,
                    )[0]
                response = await client.query_points(
                    collection_name=collection,
                    query=encoded[cache_key],
                    using=name,
                    query_filter=models.Filter(
                        must=[
                            publication_filter(publications),
                            models.FieldCondition(
                                key="model_version" if keyframes else f"{name}_embedding_version",
                                match=models.MatchValue(value=encoder.model_version),
                            ),
                            models.FieldCondition(
                                key="chunk_ids", match=models.MatchAny(any=list(frames))
                            )
                            if keyframes
                            else models.HasIdCondition(has_id=list(frames)),
                        ]
                    ),
                    limit=pool,
                    score_threshold=threshold,
                    with_payload=True,
                )
                identifiers = []
                for point in response.points:
                    if keyframes:
                        payload = point.payload or {}
                        for chunk in payload.get("chunk_ids", []):
                            if chunk not in frames:
                                continue
                            parent = records[chunk].payload
                            if (
                                payload.get("video_id") == parent.get("video_id")
                                and payload.get("ingestion_run_id")
                                == parent.get("ingestion_run_id")
                                and payload.get("semantic_scene_id")
                                == parent.get("semantic_scene_id")
                                and str(point.id) in parent.get("keyframe_ids", [])
                            ):
                                identifiers.append(chunk)
                    elif str(point.id) in frames:
                        if point.payload != records[str(point.id)].payload:
                            raise PublicationChangedError("Chunk metadata changed during retrieval")
                        identifiers.append(str(point.id))
                rankings.append(RankedList(signal, list(dict.fromkeys(identifiers))))
                signals.append(signal)
                metrics[f"{signal}_raw_candidates"] = len(response.points)
                metrics[f"{signal}_chunks"] = len(set(identifiers))
                vector_searches += 1
                vector_hits |= bool(identifiers)
            except PublicationChangedError:
                raise
            except Exception:
                degraded = True
                logger.exception("Retrieval signal failed: {}", signal)
            finally:
                metrics[f"{signal}_duration_ms"] = (time.perf_counter() - source_started) * 1000

        if frames and publications:
            if mode in ("hybrid", "visual", "siglip"):
                encoder = self._encoder or get_siglip_encoder()
                floor = max(min_score, tuning.visual_floor)
                await ann(
                    settings.qdrant.chunk_collection,
                    "siglip",
                    "chunk_siglip",
                    encoder,
                    floor,
                )
                await ann(
                    settings.qdrant.keyframe_collection,
                    "siglip",
                    "keyframe_siglip",
                    encoder,
                    floor,
                    keyframes=True,
                )
            if mode in ("hybrid", "visual", "qwen", "caption"):
                encoder = self._caption_encoder or get_qwen_encoder()
                if (
                    self._caption_encoder is not None
                    or mode in ("qwen", "caption")
                    or _qwen_is_ready(encoder)
                ):
                    if mode != "caption":
                        await ann(
                            settings.qdrant.chunk_collection,
                            "qwen",
                            "chunk_qwen",
                            encoder,
                            max(min_score, tuning.qwen_visual_floor),
                        )
                    if mode in ("hybrid", "caption"):
                        await ann(
                            settings.qdrant.chunk_collection,
                            "caption",
                            "caption_vector",
                            encoder,
                            max(min_score, tuning.caption_floor),
                        )
                else:
                    degraded = True
        if mode in ("hybrid", "caption"):
            lexical_started = time.perf_counter()
            lexical = []
            terms = set(re.findall(r"\w+", parsed.embedding_text.casefold()))
            for identifier, frame in frames.items():
                verdict = verdicts[identifier]
                overlap = len(
                    terms
                    & set(
                        re.findall(
                            r"\w+", f"{frame.caption} {' '.join(frame.retrieval_tags)}".casefold()
                        )
                    )
                )
                if verdict is not None and (overlap or verdict.confirmed):
                    lexical.append((len(verdict.confirmed), overlap, identifier))
            lexical.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
            rankings.append(RankedList("caption_lexical", [entry[2] for entry in lexical]))
            signals.append("caption_lexical")
            metrics["caption_lexical_candidates"] = len(lexical)
            metrics["caption_lexical_duration_ms"] = (time.perf_counter() - lexical_started) * 1000
        fusion_started = time.perf_counter()
        fused = reciprocal_rank_fusion(rankings)
        metrics["fusion_duration_ms"] = (time.perf_counter() - fusion_started) * 1000
        metrics["fused_chunks"] = len(fused)
        candidates = []
        for item in fused:
            frame = frames[item.id]
            verdict = verdicts[item.id]
            if verdict is not None:
                frame = replace(
                    frame,
                    metadata={
                        **(frame.metadata or {}),
                        "search_verification": {
                            "status": "uncertain" if verdict.unknown else "verified",
                            "scope": "recognized_constraints",
                            "unknown": list(verdict.unknown),
                            "matching_timestamps_ms": list(verdict.matching_timestamps_ms),
                        },
                    },
                )
                candidates.append(
                    VideoMatch(
                        frame,
                        item.score,
                        1,
                        confirmed=verdict.confirmed,
                        denied=verdict.denied,
                        signals=dict(item.contributions) if explain else {},
                    )
                )
        if granularity == "frame":
            candidates = await self._frame_matches(
                candidates, records, parsed, filters, strict=strict
            )
            references: dict[str, set[str]] = {}
            for point in records.values():
                references.setdefault(point.payload["video_id"], set()).update(
                    point.payload["keyframe_ids"]
                )
            totals = Counter({video: len(keys) for video, keys in references.items()})
        if use_rerank and candidates:
            from ml.reranker import RerankerError, get_reranker

            rerank_started = time.perf_counter()
            try:
                candidates = await asyncio.to_thread(
                    get_reranker().rerank, query, candidates, top_k=tuning.rerank_top_k
                )
                candidates.sort(key=lambda match: (-match.score, match.keyframe.point_id))
                signals.append("rerank")
            except RerankerError:
                degraded = True
                logger.exception("Reranking failed; retaining retrieval ranking")
            metrics["rerank_duration_ms"] = (time.perf_counter() - rerank_started) * 1000
        grouping_started = time.perf_counter()
        grouped = group_chunks(candidates, totals)
        metrics["grouping_duration_ms"] = (time.perf_counter() - grouping_started) * 1000
        metrics["grouped_videos"] = len(grouped)
        generation = int(
            fingerprint(
                "published-search",
                {
                    "publications": snapshot.identity,
                    "models": {
                        "qwen": settings.ml.qwen_model_name,
                        "siglip": settings.ml.model_version,
                    },
                    "tuning": tuning.model_dump(mode="json"),
                    "ranking": [(match.keyframe.point_id, match.score) for match in grouped],
                    "signals": signals,
                    "degraded": degraded,
                },
            ),
            16,
        )
        if await active_publications(ids) != publications:
            raise PublicationChangedError("Publication changed during retrieval")
        page, token = self._paginate(
            grouped,
            query=query,
            parsed=parsed,
            mode=mode,
            cursor=cursor,
            limit=limit,
            video_ids=video_ids,
            min_score=min_score,
            strict=strict,
            generation=generation,
            filters=filters,
            granularity=granularity,
            rerank=use_rerank,
        )
        # Redis invalidation is best effort. Check the bounded result set against
        # Qdrant so a cached caption cannot verify a newer caption vector.
        selected = list(
            {item.id for item in fused}
            if granularity == "frame"
            else {
                frame.point_id
                for match in page
                for frame in (match.keyframe, *match.matched_keyframes)
            }
        )
        for start in range(0, len(selected), 256):
            identifiers = selected[start : start + 256]
            fresh = await client.retrieve(
                collection_name=settings.qdrant.chunk_collection,
                ids=identifiers,
                with_payload=True,
                with_vectors=False,
            )
            if {str(point.id) for point in fresh} != set(identifiers) or any(
                point.payload != records[str(point.id)].payload for point in fresh
            ):
                raise PublicationChangedError("Result metadata changed during retrieval")
        if await active_publications(ids) != publications:
            raise PublicationChangedError("Publication changed before returning results")
        logger.bind(search_metrics=metrics).debug("Retrieval completed")
        return SearchOutcome(
            parsed=parsed,
            matches=tuple(page),
            total_videos=len(grouped),
            total_keyframes=len(candidates),
            exhaustive=False,
            signals_used=tuple(signals),
            next_cursor=token,
            took_ms=(time.perf_counter() - started) * 1000,
            degraded=degraded,
            similarity_floor=max(
                min_score,
                tuning.qwen_visual_floor
                if mode == "qwen"
                else tuning.caption_floor
                if mode == "caption"
                else tuning.visual_floor,
            ),
            below_threshold=bool(vector_searches)
            and not vector_hits
            and not grouped
            and not degraded,
            unconfirmed_concepts=tuple(
                concept for concept in parsed.required if concept not in observed_concepts
            )
            if not grouped
            else (),
        )

    def _paginate(
        self,
        grouped: list[VideoMatch],
        *,
        query: str,
        parsed: ParsedQuery,
        mode: SearchMode,
        cursor: str | None,
        limit: int,
        video_ids: list[str] | None,
        min_score: float,
        strict: bool,
        generation: int,
        rerank: bool = False,
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
    ) -> tuple[list[VideoMatch], str | None]:
        # The fingerprint covers the mode as well as the query: the same sentence
        # searched with a different set of towers is a different ranking, and
        # resuming across the two would skip and repeat videos.
        expected = fingerprint(
            query,
            {
                "mode": mode,
                "rerank": rerank,
                "required": sorted(parsed.required),
                "excluded": sorted(parsed.excluded),
                "video_ids": sorted(video_ids or []),
                "min_score": min_score,
                "strict": strict,
                # The page size feeds the candidate pool
                # (`min(max(pool, limit * 10), MAX_POOL)`), so changing it changes
                # every fused score the cursor was minted against.
                "limit": limit,
                # A reload re-ranks everything: fused scores shift and a video's
                # representative keyframe can change, so the (score, id) the cursor
                # resumes from no longer identifies the same position. Better to
                # reject the cursor and restart than to silently duplicate and skip.
                "generation": generation,
                "filters": filters.model_dump(exclude_none=True) if filters else {},
            },
            granularity=granularity or "any",
        )

        remaining = grouped
        offset = 0
        if cursor:
            decoded = decode_cursor(cursor, expected_fingerprint=expected)
            remaining = apply_cursor([_CursorView(match) for match in grouped], decoded)
            remaining = [view.match for view in remaining]
            offset = decoded.offset

        page = remaining[:limit]
        if len(remaining) <= limit or not page:
            return page, None

        last = page[-1]
        token = Cursor(
            fingerprint=expected,
            last_score=float(last.score),
            last_id=last.keyframe.point_id,
            offset=offset + len(page),
        ).encode()
        return page, token


_engine: SceneSearchEngine | None = None


@dataclass(frozen=True)
class _CursorView:
    """Adapts a match to the ``(score, id)`` shape ``apply_cursor`` expects."""

    match: VideoMatch

    @property
    def score(self) -> float:
        return self.match.score

    @property
    def id(self) -> str:
        return self.match.keyframe.point_id


def get_search_engine() -> SceneSearchEngine:
    """Return the process-wide search engine."""

    global _engine
    if _engine is None:
        _engine = SceneSearchEngine()
    return _engine


def reset_search_engine() -> None:
    """Drop the cached engine (used by tests)."""

    global _engine
    _engine = None
