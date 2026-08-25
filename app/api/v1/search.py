"""Semantic scene-search endpoint.

Maps the retrieval outcome onto the response contract in
:mod:`schemas.search`. Two mappings are worth stating because they are the ones a
reader is most likely to assume differently:

``total`` counts **videos**, not keyframes. Results are one per video, so a total
that counted keyframes would disagree with the list it describes and would tell
an engineer sizing a training set the wrong number. The keyframe count is
reported separately.

``thumbnail_url`` points at this API rather than at object storage. A presigned
URL would require the browser to reach the object store directly, which it
generally cannot, and would put a credentialed URL in the page. The proxy in
:mod:`api.v1.media` keeps the URL stable, relative, and cacheable.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from core.config import get_settings
from schemas.search import SearchRequest, SearchResponse, SearchResult
from search.cursor import CursorError
from search.engine import SearchOutcome, VideoMatch, get_search_engine

router = APIRouter(prefix="/search", tags=["search"])

# Keyframes are instants, but a result the user can watch needs a span, so each
# one is presented as a short window opening at the matched moment. This is a
# presentation default, not a claim that the index stores segments.
KEYFRAME_WINDOW_S = 4.0


def _to_result(match: VideoMatch) -> SearchResult:
    keyframe = match.keyframe
    end_timestamp = keyframe.end_timestamp_s or (keyframe.timestamp_s + KEYFRAME_WINDOW_S)
    objects_list: list[str] = []
    if keyframe.retrieval_tags:
        objects_list.extend(keyframe.retrieval_tags)
    if keyframe.vehicles:
        objects_list.extend(keyframe.vehicles)
    if keyframe.people:
        objects_list.extend(keyframe.people)
    objects_list.extend(value for value in keyframe.objects if value not in objects_list)

    return SearchResult(
        id=keyframe.point_id,
        video_id=keyframe.video_id,
        granularity=keyframe.granularity,
        ts_start_s=keyframe.timestamp_s,
        ts_end_s=end_timestamp,
        video_second=keyframe.timestamp_s,
        score=match.score,
        thumbnail_url=(
            f"/api/v1/media/thumbnail/{keyframe.point_id}" if keyframe.has_thumbnail else None
        ),
        preview_url=(f"/api/v1/media/clip/{keyframe.point_id}" if keyframe.video_key else None),
        caption=keyframe.caption or None,
        frame_no=keyframe.frame_no if keyframe.frame_no >= 0 else None,
        objects=objects_list,
        weather=keyframe.weather,
        time_of_day=keyframe.time_of_day,
        scene_type=keyframe.scene_type,
        retrieval_tags=list(keyframe.retrieval_tags),
        metadata=keyframe.metadata,
        keyframes_matched=match.keyframes_matched,
        keyframes_in_video=match.keyframes_in_video,
        contradicting_moments=match.contradicting_moments,
        confirmed=list(match.confirmed),
        denied=list(match.denied),
        matched_moments=[
            {
                "id": moment.point_id,
                "timestamp_s": moment.timestamp_s,
                "ts_start_s": moment.timestamp_s,
                "ts_end_s": moment.end_timestamp_s or (moment.timestamp_s + KEYFRAME_WINDOW_S),
                "granularity": moment.granularity,
                "video_second": moment.timestamp_s,
                "caption": moment.caption,
                "frame_no": moment.frame_no if moment.frame_no >= 0 else None,
                "weather": moment.weather,
                "time_of_day": moment.time_of_day,
                "scene_type": moment.scene_type,
                "retrieval_tags": list(moment.retrieval_tags),
                "is_primary": moment.point_id == keyframe.point_id,
                "thumbnail_url": (
                    f"/api/v1/media/thumbnail/{moment.point_id}" if moment.has_thumbnail else None
                ),
            }
            for moment in match.matched_keyframes
        ],
        score_breakdown=dict(match.signals) or None,
    )


def _to_response(request: SearchRequest, outcome: SearchOutcome) -> SearchResponse:
    return SearchResponse(
        query=request.query,
        filters_applied=request.filters,
        results=[_to_result(match) for match in outcome.matches],
        total=outcome.total_videos,
        total_keyframes=outcome.total_keyframes,
        interpreted_query=outcome.parsed.semantic_text,
        required_concepts=list(outcome.parsed.required),
        excluded_concepts=list(outcome.parsed.excluded),
        unmatched_terms=list(outcome.parsed.unmatched_exclusions),
        exhaustive=outcome.exhaustive,
        signals_used=list(outcome.signals_used),
        similarity_floor=outcome.similarity_floor,
        below_threshold=outcome.below_threshold,
        degraded=outcome.degraded,
        unconfirmed_concepts=list(outcome.unconfirmed_concepts),
        next_cursor=outcome.next_cursor,
        took_ms=outcome.took_ms,
        model_version=get_settings().ml.model_version,
    )


@router.post("", response_model=SearchResponse, summary="Search scenes by description")
async def search_scenes(request: SearchRequest) -> SearchResponse:
    """Find keyframes matching a natural-language description.

    Returns one result per video -- the best keyframe that satisfies the query --
    so twenty results mean twenty different clips. When the query names a concept
    the search knows, the result set is complete rather than a top-k sample, and
    ``exhaustive`` says which of the two happened.

    An empty list is a real answer here, not a failure: a subject this corpus does
    not contain returns nothing, with ``below_threshold`` set, rather than the
    nearest unrelated footage. Check that field before reporting "no results" so
    the reason reaches the user.
    """

    search_settings = get_settings().search
    effective_mode = request.mode
    if effective_mode is None or (effective_mode == "hybrid" and search_settings.mode != "hybrid"):
        effective_mode = search_settings.mode

    engine = get_search_engine()
    try:
        outcome = await engine.search(
            request.query,
            limit=request.limit,
            cursor=request.cursor,
            mode=effective_mode,
            filters=request.filters,
            granularity=request.granularity,
            video_ids=request.filters.video_ids,
            min_score=request.min_score,
            explain=request.explain,
            require=request.require,
            exclude=request.exclude,
            agentic=request.agentic,
            rerank=request.rerank,
        )
    except CursorError as exc:
        # A stale or foreign cursor is a bad request. Returning a 500 here would
        # send the reader looking for a server fault.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("Scene search failed for query {query!r}", query=request.query)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search is unavailable; the vector index or encoder could not be reached",
        ) from exc

    return _to_response(request, outcome)


__all__ = ["router"]
