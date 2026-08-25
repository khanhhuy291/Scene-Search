"""Scene retrieval over the hybrid keyframe index.

The collection this process currently reads is Huy's live Viettech index
(``Scences``): named vectors ``qwen`` (2048d) and ``siglip`` (768d), plus payload
keys for media and (when present) captions. ``SEARCH_CAPTION_VECTOR`` is empty on
that collection, and many points have no caption text yet — VLM enrichment is
still Huy's workstream. Attribute constraints are resolved from structured
payload fields first, then from captions when they exist (see :mod:`search.query`).

Five behaviours make up the search, and each exists because the obvious version
of it is wrong:

**Candidates come from two directions, not one.** Approximate nearest-neighbour
search is good at phrasings the captions never use and structurally incapable of
completeness. A caption scan is exhaustive for concepts it knows and blind to
paraphrase. Neither alone answers "every snowy video"; the union does, and
reciprocal rank fusion combines them without inventing a scale to compare a
cosine against a keyword hit.

**Similarity has a floor, and only the vector signals are held to it.** A
nearest-neighbour search always returns neighbours: ask for something the corpus
does not contain and it returns the least-unrelated footage, ranked confidently.
The floor (``SEARCH_VISUAL_FLOOR``, calibrated in :class:`core.config.SearchSettings`)
is what makes "spiderman" return nothing instead of every dashcam clip. It is not
applied to the caption scan, because a caption that says "snow is falling" is
direct evidence and does not need a cosine's permission to count. Qwen's own
floor is far lower and uncalibrated, so hybrid and qwen modes still consult the
SigLIP floor as the out-of-domain gate rather than letting Qwen fill the page
with unrelated clips.

**A concept the query names is a filter, not a preference.** Under
``strict_concepts`` a required concept must be positively confirmed by the
caption; a frame whose caption never mentions snow is not a snowy frame, and
admitting it because the vector liked it produces a result the user cannot
distinguish from a bug. Exclusions were always hard.

**Filtering happens per keyframe, before grouping.** "A rainy day without people"
is a property of a moment, not of a video: nearly every video in this corpus has
a pedestrian in *some* frame, so a video-level exclusion would reject almost the
entire corpus. Admissibility is decided per keyframe and grouping happens after.

**One result per video, and preferably one that renders.** Twenty near-identical
keyframes from one clip is a worse answer than twenty different clips, and for
the training-set use case it is actively misleading about how much footage was
found. Each video contributes its best admissible keyframe and reports how many
others matched.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from loguru import logger

from core.config import get_settings
from ml.encoder import get_encoder, get_qwen_encoder, get_siglip_encoder
from schemas.search import Granularity, SearchFilters
from search.catalog import CatalogView, ConceptArrays, Keyframe, KeyframeCatalog, get_catalog
from search.cursor import Cursor, apply_cursor, decode_cursor, fingerprint
from search.fusion import RankedList, reciprocal_rank_fusion
from search.query import (
    CaptionVerdict,
    ParsedQuery,
    _has_non_ascii_letters,
    concept_embed_gloss,
    parse_query,
)

SearchMode = Literal["hybrid", "visual", "caption", "qwen", "siglip"]

# Defaults matching the live Viettech collection. Runtime reads
# ``settings.search.visual_vector`` / ``caption_vector`` instead of these.
VISUAL_VECTOR = "siglip"
CAPTION_VECTOR = ""

# Candidate pool sizes, in keyframes. The concept-backed number is smaller
# because the caption scan already guarantees completeness there and the ANN pool
# only needs to add paraphrase recall. Without that guarantee the pool is the only
# source of recall, so it is deliberately far larger than the page size.
POOL_WITH_CONCEPTS = 400
POOL_SEMANTIC_ONLY = 1500
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


def _ocr_mentioned(ocr: str, query: str) -> bool:
    token = ocr.strip()
    if not token or not query.strip():
        return False
    return re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", query, re.IGNORECASE) is not None


def _ocr_lookup_token(parsed: ParsedQuery, view: CatalogView) -> str | None:
    """When the whole query *is* an OCR string stored on a keyframe.

    ``BROOKLYN`` has no lexicon concept, so without this the only recall path is
    ANN -- which cannot promise completeness and fails outright on a collection
    that does not expose ``siglip_visual``. Matching the stored OCR field keeps
    that query answerable from the payload alone.
    """

    if parsed.has_concepts:
        return None
    needle = parsed.semantic_text.strip()
    if not needle:
        return None
    return view.ocr_by_value.get(needle.casefold())


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
    # A lower bound -- see KeyframeCatalog.contradicting_positions.
    contradicting_moments: dict[str, int] = field(default_factory=dict)


class SceneSearchEngine:
    """Retrieval against the hybrid keyframe collection."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        catalog: KeyframeCatalog | None = None,
        encoder: Any | None = None,
        caption_encoder: Any | None = None,
        collection: str | None = None,
    ) -> None:
        self._client = client
        self._catalog = catalog
        self._encoder = encoder
        self._caption_encoder = caption_encoder
        self._collection = collection

    # -- collaborators -----------------------------------------------------

    def _qdrant(self) -> Any:
        if self._client is not None:
            return self._client
        from infrastructure.qdrant import get_qdrant_client

        return get_qdrant_client()

    def _collection_name(self) -> str:
        return self._collection or get_settings().qdrant.collection

    def _text_encoder(self) -> Any:
        return self._encoder if self._encoder is not None else get_encoder()

    def _caption_tower(self) -> Any | None:
        if self._caption_encoder is not None:
            return self._caption_encoder
        caption_vec = get_settings().search.caption_vector
        disabled = ("none", "null", "false", "disabled", "off", "0")
        if not caption_vec or caption_vec.lower() in disabled:
            return None
        return get_encoder()

    # -- retrieval ---------------------------------------------------------

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
        parsed = parse_query(query)
        if require is not None:
            parsed = replace(parsed, required=tuple(dict.fromkeys(require)))
        if exclude is not None:
            parsed = replace(parsed, excluded=tuple(dict.fromkeys(exclude)))

        tuning = get_settings().search
        if mode is None:
            mode = tuning.mode
        use_agentic = tuning.agentic_enabled if agentic is None else agentic
        if not use_agentic:
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
            )
        else:
            from search.agent import get_agent_orchestrator

            orchestrator = get_agent_orchestrator()

            async def _executor(
                step_parsed: ParsedQuery,
                step_hyde: str | None,
                step_signals: list[str],
            ) -> SearchOutcome:
                return await self._execute_core_search(
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
                )

            outcome, _ = await orchestrator.execute(
                raw_query=query,
                parsed=parsed,
                retrieval_executor=_executor,
            )

        should_rerank = tuning.rerank_enabled if rerank is None else rerank
        if should_rerank and outcome.matches:
            from ml.reranker import get_reranker

            reranker = get_reranker()
            reranked_matches = await asyncio.to_thread(
                reranker.rerank, query, outcome.matches, top_k=limit
            )
            outcome = replace(
                outcome,
                matches=tuple(reranked_matches),
                signals_used=(*outcome.signals_used, "rerank")
                if "rerank" not in outcome.signals_used
                else outcome.signals_used,
            )

        return outcome

    async def _execute_core_search(
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
    ) -> SearchOutcome:
        started = time.perf_counter()

        tuning = get_settings().search
        strict_concepts = tuning.strict_concepts if strict is None else strict
        visual_floor = max(tuning.visual_floor, min_score)
        caption_floor = max(tuning.caption_floor, min_score)

        embedding_query_text = hyde_caption if hyde_caption else parsed.embedding_text

        catalog = self._catalog or get_catalog()
        client = self._qdrant()
        await catalog.ensure_loaded(client)
        # One pinned view for the whole request. Reading through the mutable
        # catalog across an await lets a background reload swap the frame
        # tuple out from under the positionally-aligned concept arrays.
        view = catalog.view()
        ocr_token = _ocr_lookup_token(parsed, view)
        # The live Qwen index currently stores no captions. Strict silence-as-
        # veto would then reject every ANN hit, which reads as a dead search
        # rather than "this corpus is visual-only". Keep the caller's strict
        # flag for captioned frames and for completeness claims; only skip the
        # silence veto on frames that have no caption *and* a captionless
        # catalog. Exclusions still run in visual space for that corpus.
        captionless = view.captionless

        pool = POOL_WITH_CONCEPTS if parsed.has_concepts else POOL_SEMANTIC_ONLY
        pool = min(max(pool, limit * 10), MAX_POOL)

        ranked_lists: list[RankedList] = []
        signals_used: list[str] = list(extra_signals)
        # Distinguishes "the vector search ran and everything it found was too far
        # away" from "the vector search did not run". Only the first one means the
        # corpus does not contain the subject.
        vector_signals_ran = False
        vector_signals_found = False
        # A tower that *errored* is not a tower that found nothing. Without this
        # distinction a Qdrant outage is reported as a complete, authoritative
        # empty answer -- the single most misleading response this API can send.
        degraded = False

        candidate_cache: dict[str, Keyframe] = {}

        async def add_ann(
            *,
            signal: str,
            vector_name: str,
            encoder: Any | None = None,
            min_score: float,
        ) -> None:
            nonlocal degraded, vector_signals_ran, vector_signals_found
            ids = await self._ann_candidates(
                client,
                embedding_query_text,
                vector_name=vector_name,
                limit=pool,
                video_ids=video_ids,
                min_score=min_score,
                encoder=encoder,
                parsed=parsed,
                strict=strict_concepts,
                candidate_cache=candidate_cache,
                filters=filters,
                granularity=granularity,
            )
            if ids is None:
                degraded = True
                return
            vector_signals_ran = True
            if ids:
                vector_signals_found = True
                ranked_lists.append(RankedList(signal=signal, ids=ids))
                signals_used.append(signal)

        injected = self._encoder
        if mode == "qwen":
            qwen_floor = tuning.qwen_visual_floor if min_score == 0.0 else min_score
            await add_ann(
                signal="qwen",
                vector_name="qwen",
                encoder=injected if injected is not None else get_qwen_encoder(),
                min_score=qwen_floor,
            )
        elif mode == "siglip":
            await add_ann(
                signal="siglip",
                vector_name="siglip",
                encoder=injected if injected is not None else get_siglip_encoder(),
                min_score=visual_floor,
            )
        elif mode == "visual":
            visual_encoder = injected
            if visual_encoder is None:
                visual_encoder = (
                    get_qwen_encoder() if tuning.visual_vector == "qwen" else get_siglip_encoder()
                )
            await add_ann(
                signal="visual",
                vector_name=tuning.visual_vector,
                encoder=visual_encoder,
                min_score=visual_floor,
            )
        elif mode == "hybrid":
            # SigLIP first
            visual_vec = "siglip" if tuning.visual_vector == "qwen" else tuning.visual_vector
            await add_ann(
                signal="visual",
                vector_name=visual_vec,
                encoder=injected if injected is not None else get_siglip_encoder(),
                min_score=visual_floor,
            )
            visual_in_domain = vector_signals_found
            qwen_encoder = injected if injected is not None else get_qwen_encoder()
            # Skip Qwen when SigLIP already called the query out-of-domain.
            # Uncalibrated Qwen neighbours would otherwise replace an honest empty
            # answer with hundreds of dashcam clips. Vietnamese queries are the
            # exception: SigLIP may miss them when the gloss is empty, and Qwen
            # is the tower that can still match.
            qwen_worth_trying = visual_in_domain or _has_non_ascii_letters(parsed.semantic_text)
            if qwen_worth_trying and (injected is not None or _qwen_is_ready(qwen_encoder)):
                qwen_floor = tuning.qwen_visual_floor if min_score == 0.0 else min_score
                await add_ann(
                    signal="qwen",
                    vector_name="qwen",
                    encoder=qwen_encoder,
                    min_score=qwen_floor,
                )

        if mode in ("hybrid", "caption"):
            caption_ids = await self._caption_ann_candidates(
                client,
                embedding_query_text,
                limit=pool,
                video_ids=video_ids,
                min_score=caption_floor,
                filters=filters,
                granularity=granularity,
            )
            if caption_ids is None:
                degraded = True
            else:
                vector_signals_ran = True
                if caption_ids:
                    vector_signals_found = True
                    ranked_lists.append(RankedList(signal="caption_vector", ids=caption_ids))
                    signals_used.append("caption_vector")
        concepts = await catalog.concept_arrays(
            view, tuple(parsed.required) + tuple(parsed.excluded)
        )

        # The caption scan is the only exhaustive signal, and the only one that
        # can answer a concept query completely. It is not subject to the
        # similarity floor: its evidence is the caption text, not a cosine.
        # Gated on mode for the same reason the towers are: the ablations exist
        # so the contribution of each signal can be *seen*, and a "visual only"
        # run that quietly includes the caption scan overstates the visual tower
        # by whatever the scan contributed.
        lexical_ids: list[str] = []
        if mode in ("hybrid", "caption", "qwen", "siglip"):
            lexical_ids = self._lexical_candidates(
                view,
                parsed,
                concepts,
                video_ids=video_ids,
                ocr_token=ocr_token,
                filters=filters,
                granularity=granularity,
            )
        if lexical_ids:
            ranked_lists.append(RankedList(signal="caption_text", ids=lexical_ids))
            signals_used.append("caption_text")

        # A required concept nothing in the corpus confirms is worth naming: it is
        # the difference between "no results" and "no caption anywhere mentions
        # snow", and only the second tells the user which word to drop.
        unconfirmed = tuple(
            concept
            for concept in parsed.required
            if "present" not in concepts.get(concept, ((), ()))[0]
        )

        if not ranked_lists:
            # Nothing ranked anything. Returning an empty page is correct; the
            # alternative is to relax the query silently, which hides the reason.
            return SearchOutcome(
                parsed=parsed,
                matches=(),
                total_videos=0,
                total_keyframes=0,
                exhaustive=parsed.has_concepts and not degraded,
                signals_used=(),
                next_cursor=None,
                took_ms=(time.perf_counter() - started) * 1000.0,
                similarity_floor=visual_floor,
                below_threshold=vector_signals_ran and not vector_signals_found,
                unconfirmed_concepts=unconfirmed,
                degraded=degraded,
            )

        # How many moments in each returned clip positively show something the
        # query excluded. See KeyframeCatalog.contradicting_positions for why
        # this is a lower bound and must be labelled as one.
        contradicting = catalog.contradicting_positions(view, concepts, parsed.excluded)

        admissible, unknown_candidates = self._admissible_keyframes(
            view,
            parsed,
            concepts,
            ranked_lists,
            strict=strict_concepts,
            ocr_token=ocr_token,
            candidate_cache=candidate_cache,
            filters=filters,
            granularity=granularity,
        )
        if captionless and parsed.excluded and mode != "caption" and admissible:
            banned = await self._visual_exclusion_ids(
                client,
                parsed,
                mode=mode,
                candidate_ids=list(admissible.keys()),
                video_ids=video_ids,
                min_score=visual_floor if mode != "qwen" else min_score,
            )
            if banned:
                admissible = {
                    point_id: item
                    for point_id, item in admissible.items()
                    if point_id not in banned
                }
        filtered = [
            replace(ranked, ids=[point_id for point_id in ranked.ids if point_id in admissible])
            for ranked in ranked_lists
        ]
        fused = reciprocal_rank_fusion([r for r in filtered if r.ids])

        grouped = self._group_by_video(
            fused, admissible, explain=explain, view=view, contradicting=contradicting
        )

        page, next_token = self._paginate(
            grouped,
            query=query,
            parsed=parsed,
            mode=mode,
            cursor=cursor,
            limit=limit,
            video_ids=video_ids,
            min_score=min_score,
            strict=strict_concepts,
            generation=view.generation,
            filters=filters,
            granularity=granularity,
        )

        return SearchOutcome(
            parsed=parsed,
            matches=tuple(page),
            total_videos=len(grouped),
            total_keyframes=len(admissible),
            # Completeness is claimed only when the caption scan actually ran
            # over a snapshot that still describes the collection, with concepts
            # enforced as hard filters. `unknown_candidates` counts points the
            # vector search returned that the snapshot has never seen, which is
            # direct evidence the scan could not have been exhaustive.
            exhaustive=(
                parsed.has_concepts
                and bool(lexical_ids)
                and strict_concepts
                and not captionless
                and not degraded
                and unknown_candidates == 0
            ),
            signals_used=tuple(signals_used),
            next_cursor=next_token,
            took_ms=(time.perf_counter() - started) * 1000.0,
            similarity_floor=visual_floor,
            # A floored-out vector search is only the reason for an empty answer
            # if the answer *is* empty. The caption scan is exempt from the
            # floor, so it can return results while every cosine fell short.
            below_threshold=vector_signals_ran and not vector_signals_found and not page,
            unconfirmed_concepts=unconfirmed,
            degraded=degraded,
            stale_candidates=unknown_candidates,
            contradicting_moments=contradicting,
        )

    # -- candidate sources -------------------------------------------------

    async def _ann_candidates(
        self,
        client: Any,
        text: str,
        *,
        vector_name: str,
        limit: int,
        video_ids: list[str] | None,
        min_score: float,
        encoder: Any | None = None,
        point_ids: list[str] | None = None,
        parsed: ParsedQuery | None = None,
        strict: bool = False,
        candidate_cache: dict[str, Keyframe] | None = None,
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
    ) -> list[str] | None:
        try:
            enc = encoder or self._text_encoder()
            if enc is self._encoder or enc is self._caption_encoder:
                # Injected encoders are test/evaluation collaborators and are
                # expected to control their own execution model.
                encoded = enc.encode_texts([text])
            else:
                encoded = await asyncio.to_thread(enc.encode_texts, [text])
            vector = encoded[0]
        except Exception:
            logger.exception(
                "Encoder could not encode query for vector {vector_name}; skipping signal",
                vector_name=vector_name,
            )
            return None
        tuning = get_settings().search
        effective_min_score = (
            max(tuning.qwen_visual_floor, min_score) if vector_name == "qwen" else min_score
        )

        return await self._query_points(
            client,
            vector,
            vector_name=vector_name,
            limit=limit,
            video_ids=video_ids,
            min_score=effective_min_score,
            point_ids=point_ids,
            parsed=parsed,
            strict=strict,
            candidate_cache=candidate_cache,
            filters=filters,
            granularity=granularity,
        )

    def _probe_tower(self, mode: SearchMode) -> tuple[Any | None, str]:
        """Encoder and named vector used to probe a concept in image space."""

        injected = self._encoder
        tuning = get_settings().search
        if mode == "qwen":
            return (injected if injected is not None else get_qwen_encoder()), "qwen"
        if mode == "siglip":
            return (injected if injected is not None else get_siglip_encoder()), "siglip"
        encoder = injected or (
            get_qwen_encoder() if tuning.visual_vector == "qwen" else get_siglip_encoder()
        )
        return encoder, tuning.visual_vector

    async def _visual_exclusion_ids(
        self,
        client: Any,
        parsed: ParsedQuery,
        *,
        mode: SearchMode,
        candidate_ids: list[str],
        video_ids: list[str] | None,
        min_score: float,
    ) -> set[str]:
        """Keyframe ids among the current matches that resemble an excluded concept.

        Captions are what make "without people" a hard filter. On a visual-only
        index there is no caption to read, so each remaining candidate is scored
        against an English gloss of the excluded concept and dropped when it
        looks like that concept. Contrastive models cannot encode negation, which
        is why this is a separate probe rather than embedding "without people"
        into the original query.

        The probe is restricted to ``candidate_ids`` so a global "people" search
        cannot miss a rainy frame that contains people but is not among the
        corpus-wide people nearest neighbours.
        """

        if not candidate_ids:
            return set()
        encoder, vector_name = self._probe_tower(mode)
        banned: set[str] = set()
        for concept in parsed.excluded:
            ids = await self._ann_candidates(
                client,
                concept_embed_gloss(concept),
                vector_name=vector_name,
                limit=len(candidate_ids),
                video_ids=video_ids,
                min_score=min_score,
                encoder=encoder,
                point_ids=candidate_ids,
            )
            if ids:
                banned.update(ids)
        return banned

    async def _query_points(
        self,
        client: Any,
        vector: list[float],
        *,
        vector_name: str,
        limit: int,
        video_ids: list[str] | None,
        min_score: float,
        point_ids: list[str] | None = None,
        parsed: ParsedQuery | None = None,
        strict: bool = False,
        candidate_cache: dict[str, Keyframe] | None = None,
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
    ) -> list[str] | None:
        kwargs: dict[str, Any] = {
            "collection_name": self._collection_name(),
            "query": vector,
            "using": vector_name,
            "limit": limit,
            "with_payload": True,
        }
        if min_score > 0:
            kwargs["score_threshold"] = min_score

        from qdrant_client.http import models

        must: list[Any] = []
        must_not: list[Any] = []
        should: list[Any] = []

        if filters is not None:
            from search.points import build_filter

            pushed = build_filter(
                dataset=filters.dataset,
                video_ids=filters.video_ids,
                weather=filters.weather,
                timeofday=filters.timeofday,
                scene=filters.scene,
                objects_any=filters.objects_any,
                objects_all=filters.objects_all,
                behaviors=filters.behaviors,
                granularity=granularity,
                time_range_s=filters.time_range_s,
            )
            if pushed is not None:
                must.extend(pushed.must or [])
                must_not.extend(pushed.must_not or [])
            for class_name, count in (filters.min_object_counts or {}).items():
                must.append(
                    models.FieldCondition(
                        key=f"object_counts.{class_name}",
                        range=models.Range(gte=count),
                    )
                )
        elif granularity is not None:
            if granularity == "segment":
                must.append(
                    models.FieldCondition(
                        key="granularity", match=models.MatchValue(value="segment")
                    )
                )
            elif granularity == "frame":
                must_not.append(
                    models.FieldCondition(
                        key="granularity", match=models.MatchValue(value="segment")
                    )
                )

        if video_ids:
            must.append(
                models.FieldCondition(key="video_id", match=models.MatchAny(any=list(video_ids)))
            )
        if point_ids:
            must.append(models.HasIdCondition(has_id=list(point_ids)))

        # Pushdown Boolean Filtering on Qdrant
        if parsed and parsed.excluded:
            for exc in parsed.excluded:
                must_not.append(
                    models.FieldCondition(
                        key="present_concepts", match=models.MatchValue(value=exc)
                    )
                )

        if parsed and parsed.required:
            if strict:
                for req in parsed.required:
                    must.append(
                        models.FieldCondition(
                            key="present_concepts", match=models.MatchValue(value=req)
                        )
                    )
            else:
                for req in parsed.required:
                    should.append(
                        models.FieldCondition(
                            key="present_concepts", match=models.MatchValue(value=req)
                        )
                    )
                    should.append(
                        models.FieldCondition(
                            key="metadata.retrieval_tags", match=models.MatchValue(value=req)
                        )
                    )

        if must or must_not or should:
            kwargs["query_filter"] = models.Filter(
                must=must or None,
                must_not=must_not or None,
                should=should or None,
            )

        try:
            response = await client.query_points(**kwargs)
        except Exception:
            logger.exception(
                "Qdrant query against {vector} failed; continuing without that signal",
                vector=vector_name,
            )
            return None

        from search.catalog import keyframe_from_payload

        result_ids: list[str] = []
        for point in response.points:
            pid = str(point.id)
            result_ids.append(pid)
            payload = getattr(point, "payload", None)
            if candidate_cache is not None and payload:
                kf = keyframe_from_payload(pid, payload)
                if kf is not None:
                    candidate_cache[pid] = kf

        return result_ids

    @staticmethod
    def _verdict_at(
        position: int,
        parsed: ParsedQuery,
        concepts: ConceptArrays,
        *,
        strict: bool,
        has_caption: bool = True,
        corpus_captionless: bool = False,
        ocr: str = "",
        ocr_token: str | None = None,
    ) -> CaptionVerdict | None:
        """Judge one keyframe from the precomputed concept arrays.

        Returns None when the query excludes it. Mirrors
        :func:`search.query.evaluate_clauses` exactly; it reads the memoized
        arrays instead of re-splitting the caption, which is the difference
        between a fast search and a two-second one.

        ``strict`` decides what an unmentioned concept means. Strict treats
        silence as failure, which is what makes a named concept an actual filter:
        these captions are long and describe weather, light and traffic
        unprompted, so a caption that never says "snow" is far better evidence of
        no snow than of an unobservant caption. Non-strict keeps such frames,
        which is only useful for measuring what strictness costs.

        Silence is only a veto when this keyframe has a caption, or when the
        catalog as a whole has captions (an empty caption on a captioned corpus
        is evidence, not missing enrichment). A fully captionless catalog cannot
        confirm required concepts from text, so unknown stays unknown rather
        than becoming a global ``strict=False``.
        """

        confirmed: list[str] = []
        denied: list[str] = []
        mentions = 0

        for concept in parsed.excluded:
            polarity = concepts[concept][0][position]
            if polarity == "present":
                return None
            if polarity == "absent":
                denied.append(concept)

        for concept in parsed.required:
            polarities, counts = concepts[concept]
            polarity = polarities[position]
            if polarity == "absent":
                return None
            if polarity == "present":
                confirmed.append(concept)
                mentions += counts[position]
            elif strict and (has_caption or not corpus_captionless):
                return None

        if ocr_token is not None and not _ocr_mentioned(ocr, ocr_token):
            return None

        return CaptionVerdict(
            admissible=True,
            confirmed=tuple(confirmed),
            denied=tuple(denied),
            mentions=mentions,
        )

    @staticmethod
    def _matches_filters(
        keyframe: Keyframe,
        filters: SearchFilters | None,
        granularity: Granularity | None,
    ) -> bool:
        """Apply the public filter contract to catalog and fresh Qdrant candidates."""

        if granularity is not None and keyframe.granularity != granularity:
            return False
        if filters is None:
            return True

        def normalized(values: list[str] | None) -> set[str]:
            return {value.strip().casefold() for value in values or []}

        if filters.video_ids and keyframe.video_id not in filters.video_ids:
            return False
        if filters.dataset and (keyframe.dataset or "").casefold() not in normalized(
            filters.dataset
        ):
            return False
        if filters.weather and (keyframe.weather or "").casefold() not in normalized(
            filters.weather
        ):
            return False
        if filters.timeofday and (keyframe.time_of_day or "").casefold() not in normalized(
            filters.timeofday
        ):
            return False
        if filters.scene and (keyframe.scene_type or "").casefold() not in normalized(
            filters.scene
        ):
            return False

        objects = {value.casefold() for value in keyframe.objects}
        any_objects = normalized(filters.objects_any)
        if any_objects and objects.isdisjoint(any_objects):
            return False
        all_objects = normalized(filters.objects_all)
        if all_objects and not all_objects.issubset(objects):
            return False

        counts = {key.casefold(): value for key, value in (keyframe.object_counts or {}).items()}
        if any(
            counts.get(name.casefold(), 0) < count
            for name, count in (filters.min_object_counts or {}).items()
        ):
            return False

        behaviors = {value.casefold() for value in keyframe.behaviors}
        required_behaviors = normalized(filters.behaviors)
        if required_behaviors and behaviors.isdisjoint(required_behaviors):
            return False

        if filters.time_range_s is not None:
            start, end = filters.time_range_s
            keyframe_end = keyframe.end_timestamp_s or keyframe.timestamp_s
            if keyframe_end < start or keyframe.timestamp_s > end:
                return False
        return True

    def _lexical_candidates(
        self,
        view: CatalogView,
        parsed: ParsedQuery,
        concepts: ConceptArrays,
        *,
        video_ids: list[str] | None,
        ocr_token: str | None = None,
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
    ) -> list[str]:
        """Every keyframe whose caption or structured fields satisfy the query.

        Ordered by how strongly the evidence confirms the query: all required
        concepts confirmed first, then by how much the caption dwells on them,
        then by explicit statements of absence for the excluded concepts. Only the
        *order* matters -- fusion uses rank and discards the magnitudes -- so this
        needs to sort sensibly, not to be calibrated.

        Runs for concept-backed queries, and also for a query that *is* an OCR
        token stored on a keyframe (``BROOKLYN``), which the lexicon cannot name.
        """

        if not parsed.has_concepts and ocr_token is None:
            return []

        allowed = set(video_ids) if video_ids else None
        scored: list[tuple[int, int, int, str]] = []
        for position, keyframe in enumerate(view.frames):
            if allowed is not None and keyframe.video_id not in allowed:
                continue
            if not self._matches_filters(keyframe, filters, granularity):
                continue
            if ocr_token is None and not parsed.has_concepts:
                continue
            if parsed.has_concepts:
                verdict = self._verdict_at(
                    position,
                    parsed,
                    concepts,
                    strict=True,
                    has_caption=bool(keyframe.caption.strip()),
                    corpus_captionless=view.captionless,
                    ocr=keyframe.ocr,
                    ocr_token=ocr_token,
                )
                if verdict is None:
                    continue
                if len(verdict.confirmed) < len(parsed.required):
                    continue
                scored.append(
                    (
                        -len(verdict.confirmed),
                        -verdict.mentions,
                        -len(verdict.denied),
                        keyframe.point_id,
                    )
                )
            elif _ocr_mentioned(keyframe.ocr, ocr_token or ""):
                scored.append((0, 0, 0, keyframe.point_id))
        scored.sort()
        return [item[3] for item in scored]

    # -- filtering and grouping -------------------------------------------

    async def _caption_ann_candidates(
        self,
        client: Any,
        text: str,
        *,
        limit: int,
        video_ids: list[str] | None,
        min_score: float,
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
    ) -> list[str] | None:
        tower = self._caption_tower()
        if tower is None:
            return []
        vec_name = get_settings().search.caption_vector
        return await self._ann_candidates(
            client,
            text,
            vector_name=vec_name,
            limit=limit,
            video_ids=video_ids,
            min_score=min_score,
            encoder=tower,
            filters=filters,
            granularity=granularity,
        )

    def _admissible_keyframes(
        self,
        view: CatalogView,
        parsed: ParsedQuery,
        concepts: ConceptArrays,
        ranked_lists: list[RankedList],
        *,
        strict: bool,
        ocr_token: str | None = None,
        candidate_cache: dict[str, Keyframe] | None = None,
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
    ) -> tuple[dict[str, tuple[Keyframe, CaptionVerdict]], int]:
        """Resolve candidates to keyframes and drop the ones the query rules out."""

        admissible: dict[str, tuple[Keyframe, CaptionVerdict]] = {}
        seen: set[str] = set()
        unknown = 0
        for ranked in ranked_lists:
            for point_id in ranked.ids:
                if point_id in seen:
                    continue
                seen.add(point_id)
                keyframe: Keyframe | None = None
                position = view.position_of(point_id) if view else None
                if position is not None:
                    keyframe = view.frames[position]
                elif candidate_cache and point_id in candidate_cache:
                    keyframe = candidate_cache[point_id]

                if keyframe is None:
                    unknown += 1
                    continue

                if not self._matches_filters(keyframe, filters, granularity):
                    continue

                if position is not None:
                    verdict = self._verdict_at(
                        position,
                        parsed,
                        concepts,
                        strict=strict,
                        has_caption=bool(keyframe.caption.strip()),
                        corpus_captionless=view.captionless if view else False,
                        ocr=keyframe.ocr,
                        ocr_token=ocr_token,
                    )
                else:
                    if ocr_token is not None and not _ocr_mentioned(keyframe.ocr, ocr_token):
                        continue

                    # Fast Stateless Payload Verdict
                    present_tags = set(getattr(keyframe, "present_concepts", ()) or ())
                    absent_tags = set(getattr(keyframe, "absent_concepts", ()) or ())
                    if not present_tags and not absent_tags and keyframe.metadata:
                        present_tags = set(keyframe.metadata.get("present_concepts") or ())
                        absent_tags = set(keyframe.metadata.get("absent_concepts") or ())

                    if present_tags or absent_tags:
                        if any(c in present_tags for c in parsed.excluded):
                            continue
                        confirmed = tuple(c for c in parsed.required if c in present_tags)
                        denied = tuple(c for c in parsed.excluded if c in absent_tags)
                        if strict and len(confirmed) < len(parsed.required):
                            continue
                        verdict = CaptionVerdict(
                            admissible=True,
                            confirmed=confirmed,
                            denied=denied,
                            mentions=len(confirmed),
                        )
                    else:
                        from search.query import evaluate_caption

                        verdict = evaluate_caption(keyframe.caption, parsed)
                        if not verdict.admissible or (
                            strict and len(verdict.confirmed) < len(parsed.required)
                        ):
                            continue

                if verdict is not None and verdict.admissible:
                    admissible[point_id] = (keyframe, verdict)
        if unknown:
            logger.warning(
                "{count} candidates were not in the keyframe catalog; the snapshot "
                "is behind the collection",
                count=unknown,
            )
        return admissible, unknown

    def _group_by_video(
        self,
        fused: list[Any],
        admissible: dict[str, tuple[Keyframe, CaptionVerdict]],
        *,
        explain: bool,
        view: CatalogView | None = None,
        contradicting: dict[str, int] | None = None,
    ) -> list[VideoMatch]:
        """Collapse keyframes to one result per video, best renderable frame winning.

        A keyframe that has both a thumbnail and a clip beats one that has
        neither, and score decides between keyframes of equal renderability.

        This orders those two the opposite way round from how it looks like it
        should. The reason is that 42% of the keyframes in this index have no
        derived media, scattered across 98% of the videos, so ranking on score
        alone filled the grid with cards that could not draw an image or open a
        player -- a result the user cannot even evaluate. Every candidate here has
        already passed the query's filters, so choosing a renderable one among
        them trades a slightly lower-ranked moment for a visible one, and only
        ever within a video that would have been listed anyway. Where a video has
        no renderable keyframe at all (6 of 881) it is still listed, on its
        caption, rather than being silently dropped from a corpus-wide count.
        """

        per_video_total: dict[str, int] = {}
        per_video_keyframes: dict[str, list[Keyframe]] = {}
        for keyframe, _ in admissible.values():
            per_video_total[keyframe.video_id] = per_video_total.get(keyframe.video_id, 0) + 1
            per_video_keyframes.setdefault(keyframe.video_id, []).append(keyframe)

        for kfs in per_video_keyframes.values():
            kfs.sort(key=lambda kf: (kf.timestamp_s, kf.point_id))

        best: dict[str, tuple[tuple[bool, float], VideoMatch]] = {}
        for result in fused:
            entry = admissible.get(result.id)
            if entry is None:
                continue
            keyframe, verdict = entry
            key = (keyframe.renderable, result.score)
            current = best.get(keyframe.video_id)
            if current is not None and current[0] >= key:
                continue
            best[keyframe.video_id] = (
                key,
                VideoMatch(
                    keyframe=keyframe,
                    score=result.score,
                    keyframes_matched=per_video_total.get(keyframe.video_id, 1),
                    keyframes_in_video=(view.keyframes_in_video(keyframe.video_id) if view else 0),
                    contradicting_moments=(contradicting or {}).get(keyframe.video_id, 0),
                    confirmed=tuple(verdict.confirmed),
                    denied=tuple(verdict.denied),
                    signals=dict(result.contributions) if explain else {},
                    matched_keyframes=tuple(per_video_keyframes.get(keyframe.video_id, [keyframe])),
                ),
            )

        matches = [entry[1] for entry in best.values()]
        # The same deterministic order the cursor is minted from: fused score
        # descending, point id ascending as the tie-break.
        matches.sort(key=lambda match: (-match.score, match.keyframe.point_id))
        return matches

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
        filters: SearchFilters | None = None,
        granularity: Granularity | None = None,
    ) -> tuple[list[VideoMatch], str | None]:
        # The fingerprint covers the mode as well as the query: the same sentence
        # searched with a different set of towers is a different ranking, and
        # resuming across the two would skip and repeat videos.
        expected = fingerprint(
            query,
            {
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


_engine: SceneSearchEngine | None = None


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


__all__ = [
    "CAPTION_VECTOR",
    "MAX_POOL",
    "POOL_SEMANTIC_ONLY",
    "POOL_WITH_CONCEPTS",
    "VISUAL_VECTOR",
    "SceneSearchEngine",
    "SearchMode",
    "SearchOutcome",
    "VideoMatch",
    "get_search_engine",
    "reset_search_engine",
]
