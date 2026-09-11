"""Retrieval behaviour: per-keyframe filtering, one result per video, completeness.

Everything here runs against fakes. The point is to pin the behaviours that are
easy to regress and expensive to notice -- an exclusion silently applied at video
level, a second copy of the same video in the results, a result set quietly
truncated to the page size -- none of which need a real index to verify.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from core.config import get_settings
from schemas.search import SearchFilters
from search.catalog import Keyframe, KeyframeCatalog
from search.engine import SceneSearchEngine
from search.query import concept_embed_gloss


def test_structured_filters_are_applied_to_catalog_candidates() -> None:
    matching = Keyframe(
        point_id="match",
        video_id="video-a",
        timestamp_s=6.0,
        frame_no=-1,
        caption="A rainy road with a car.",
        thumbnail_key="thumbnails/match.jpg",
        video_key=None,
        weather="rain",
        dataset="uploads",
        granularity="segment",
        objects=("car",),
        object_counts={"car": 2},
        behaviors=("cut_in",),
        end_timestamp_s=12.0,
    )
    filters = SearchFilters(
        dataset=["uploads"],
        weather=["rain"],
        objects_all=["car"],
        min_object_counts={"car": 2},
        behaviors=["cut_in"],
        time_range_s=(5.0, 15.0),
    )

    assert SceneSearchEngine._matches_filters(matching, filters, "segment")
    assert not SceneSearchEngine._matches_filters(matching, filters, "frame")
    assert not SceneSearchEngine._matches_filters(
        matching, filters.model_copy(update={"weather": ["snow"]}), "segment"
    )


@dataclass
class FakePoint:
    id: str
    payload: dict[str, Any]


@dataclass
class FakeScored:
    id: str
    score: float


class FakeResponse:
    def __init__(self, points: list[FakeScored]) -> None:
        self.points = points


class FakeQdrant:
    """Scrolls a fixed corpus and returns a configurable ANN ordering.

    Honours ``score_threshold`` the way Qdrant does, because the floor is the
    mechanism under test: a fake that ignored it would let every threshold test
    pass without the threshold existing.
    """

    # Comfortably above the calibrated floor, so a test that says nothing about
    # similarity gets candidates rather than an accidental empty result.
    DEFAULT_SCORE = 0.2

    def __init__(
        self,
        points: list[FakePoint],
        ann: list[str] | None = None,
        scores: dict[str, float] | None = None,
        routes: dict[tuple[float, ...], list[str]] | None = None,
        scores_by_vector: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._points = points
        # Default ANN order is corpus order, which keeps a test that does not care
        # about ranking from having to state one.
        self._ann = ann if ann is not None else [point.id for point in points]
        self._scores = scores or {}
        self._routes = routes
        self._scores_by_vector = scores_by_vector or {}
        self.queries: list[dict[str, Any]] = []

    async def scroll(self, **kwargs: Any) -> tuple[list[FakePoint], None]:
        return list(self._points), None

    async def query_points(self, **kwargs: Any) -> FakeResponse:
        self.queries.append(kwargs)
        query = kwargs.get("query")
        if self._routes is not None and query is not None:
            ids = self._routes.get(tuple(query), [])
        else:
            ids = self._ann
        limit = kwargs.get("limit", len(ids))
        threshold = kwargs.get("score_threshold")
        scored = [
            FakeScored(id=pid, score=self._score_for(pid, kwargs.get("using")))
            for pid in ids[:limit]
        ]
        if threshold is not None:
            scored = [point for point in scored if point.score >= threshold]
        return FakeResponse(scored)

    def _score_for(self, point_id: str, vector_name: str | None) -> float:
        if vector_name and vector_name in self._scores_by_vector:
            lookup = self._scores_by_vector[vector_name]
            if point_id in lookup:
                return lookup[point_id]
        return self._scores.get(point_id, self.DEFAULT_SCORE)


class FakeEncoder:
    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class DictEncoder:
    """Returns a distinct vector per query string so ANN routes can diverge."""

    def __init__(self, mapping: dict[str, list[float]], default: list[float] | None = None) -> None:
        self.mapping = mapping
        self.default = default or (next(iter(mapping.values())) if mapping else [0.1, 0.2, 0.3])

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.mapping.get(text, self.default) for text in texts]


def visual_keyframe(
    point_id: str,
    video_id: str,
    *,
    timestamp: float = 1.0,
) -> FakePoint:
    """A live-index frame: media keys, no caption, no structured attributes."""

    return FakePoint(
        id=point_id,
        payload={
            "video_id": video_id,
            "timestamp_sec": timestamp,
            "frame_no": int(timestamp * 30),
            "minio_thumbnail_key": f"thumbnails/{video_id}/{point_id}.jpg",
            "minio_video_key": f"videos/{video_id}.mov",
        },
    )


def keyframe(
    point_id: str,
    video_id: str,
    caption: str,
    *,
    timestamp: float = 0.0,
    thumbnail: bool = True,
    video: bool = True,
) -> FakePoint:
    return FakePoint(
        id=point_id,
        payload={
            "video_id": video_id,
            "timestamp_sec": timestamp,
            "frame_no": int(timestamp * 30),
            "qwen_caption": caption,
            "minio_thumbnail_key": f"thumbnails/{video_id}/{point_id}.jpg" if thumbnail else None,
            "minio_video_key": f"videos/{video_id}.mov" if video else None,
        },
    )


@pytest.fixture(autouse=True)
def pinned_tuning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the retrieval thresholds so these tests do not read a deployment's .env.

    The floor is a calibration constant that a deployment is expected to override,
    so tests that assert on it have to state the value they mean.
    """

    monkeypatch.setenv("SEARCH_VISUAL_FLOOR", "0.09")
    monkeypatch.setenv("SEARCH_CAPTION_FLOOR", "0.0")
    monkeypatch.setenv("SEARCH_STRICT_CONCEPTS", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_engine(
    points: list[FakePoint],
    ann: list[str] | None = None,
    scores: dict[str, float] | None = None,
) -> SceneSearchEngine:
    client = FakeQdrant(points, ann, scores)
    return SceneSearchEngine(
        client=client,
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        # Explicitly off: the caption tower is optional and a unit test must not
        # depend on whether a multi-gigabyte model happens to be on the machine.
        caption_encoder=None,
        collection="scenes",
    )


# -- one result per video ----------------------------------------------------


@pytest.mark.asyncio
async def test_each_video_appears_once() -> None:
    points = [
        keyframe("p1", "video-a", "A rainy street.", timestamp=1.0),
        keyframe("p2", "video-a", "More rain on the same street.", timestamp=5.0),
        keyframe("p3", "video-a", "Still raining here.", timestamp=9.0),
        keyframe("p4", "video-b", "Rain falls on a quiet road.", timestamp=2.0),
    ]
    outcome = await build_engine(points).search("rainy day", limit=10)

    video_ids = [match.keyframe.video_id for match in outcome.matches]
    assert sorted(video_ids) == ["video-a", "video-b"]
    assert outcome.total_videos == 2


@pytest.mark.asyncio
async def test_result_reports_how_many_keyframes_matched() -> None:
    points = [
        keyframe("p1", "video-a", "A rainy street.", timestamp=1.0),
        keyframe("p2", "video-a", "More rain here.", timestamp=5.0),
        keyframe("p3", "video-b", "Rain on the road.", timestamp=2.0),
    ]
    outcome = await build_engine(points).search("rainy day", limit=10)

    matched = {match.keyframe.video_id: match.keyframes_matched for match in outcome.matches}
    assert matched == {"video-a": 2, "video-b": 1}


@pytest.mark.asyncio
async def test_best_scoring_keyframe_represents_its_video() -> None:
    points = [
        keyframe("weak", "video-a", "Some rain.", timestamp=1.0),
        keyframe("strong", "video-a", "Rain, rain and more rain everywhere.", timestamp=5.0),
    ]
    # ANN ranks the strong keyframe first, and the caption evidences it more.
    outcome = await build_engine(points, ann=["strong", "weak"]).search("rainy day", limit=10)

    assert [match.keyframe.point_id for match in outcome.matches] == ["strong"]


# -- exclusions are per keyframe --------------------------------------------


@pytest.mark.asyncio
async def test_exclusion_keeps_the_clean_keyframe_of_a_video_that_shows_people() -> None:
    """The behaviour the whole design turns on.

    Nearly every video in a driving corpus contains a pedestrian at some point.
    Excluding at video level would therefore reject the corpus; the clean moment
    inside an otherwise busy video is precisely what the query asked for.
    """

    points = [
        keyframe(
            "busy", "video-a", "A rainy street with several pedestrians crossing.", timestamp=1.0
        ),
        keyframe("clean", "video-a", "A rainy street with no visible pedestrians.", timestamp=8.0),
    ]
    outcome = await build_engine(points).search("rainy day without people", limit=10)

    assert [match.keyframe.point_id for match in outcome.matches] == ["clean"]
    assert outcome.matches[0].denied == ("people",)


@pytest.mark.asyncio
async def test_exclusion_applies_to_keyframes_the_ann_supplied() -> None:
    """An exclusion must hold on candidates the vector search brought in.

    Filtering only the caption-scan candidates would let the ANN reintroduce
    exactly what the user excluded, and it would do so silently.
    """

    points = [
        keyframe(
            "has-people", "video-a", "Rain, and a crowd of people on the pavement.", timestamp=1.0
        ),
        keyframe("no-people", "video-b", "Rain on an empty road, nobody about.", timestamp=1.0),
    ]
    outcome = await build_engine(points, ann=["has-people", "no-people"]).search(
        "rainy day without people", limit=10
    )

    assert [match.keyframe.video_id for match in outcome.matches] == ["video-b"]


@pytest.mark.asyncio
async def test_keyframe_that_never_mentions_the_excluded_concept_is_kept() -> None:
    points = [keyframe("quiet", "video-a", "Rain streaks a windshield at dusk.", timestamp=1.0)]
    outcome = await build_engine(points).search("rainy day without people", limit=10)

    assert len(outcome.matches) == 1
    assert outcome.matches[0].denied == ()


@pytest.mark.asyncio
async def test_caption_contradicting_a_required_concept_is_rejected() -> None:
    points = [
        keyframe("no-snow", "video-a", "A cold winter road with no snow at all.", timestamp=1.0),
        keyframe("snow", "video-b", "Snow covers the road and the kerb.", timestamp=1.0),
    ]
    outcome = await build_engine(points, ann=["no-snow", "snow"]).search("snowy day", limit=10)

    assert [match.keyframe.video_id for match in outcome.matches] == ["video-b"]


@pytest.mark.asyncio
async def test_removing_an_inferred_exclusion_widens_the_results() -> None:
    points = [
        keyframe("busy", "video-a", "A rainy street with pedestrians crossing.", timestamp=1.0),
        keyframe("clean", "video-b", "A rainy street, no pedestrians visible.", timestamp=1.0),
    ]
    engine = build_engine(points, ann=["busy", "clean"])

    narrow = await engine.search("rainy day without people", limit=10)
    widened = await engine.search("rainy day without people", limit=10, exclude=[])

    assert narrow.total_videos == 1
    assert widened.total_videos == 2


@pytest.mark.asyncio
async def test_captionless_exclusion_drops_visually_similar_frames() -> None:
    """Live index has no captions, so "without people" has to probe image space.

    Turning strictness off without a substitute made the chip a no-op: rainy
    frames with people and rainy frames without them ranked the same.
    """

    points = [
        visual_keyframe("busy", "video-a"),
        visual_keyframe("empty", "video-b"),
    ]
    query_vec = [1.0, 0.0, 0.0]
    people_vec = [0.0, 1.0, 0.0]
    client = FakeQdrant(
        points,
        routes={
            tuple(query_vec): ["busy", "empty"],
            tuple(people_vec): ["busy"],
        },
    )
    engine = SceneSearchEngine(
        client=client,
        catalog=KeyframeCatalog(),
        encoder=DictEncoder(
            {
                "rainy day": query_vec,
                concept_embed_gloss("people"): people_vec,
            }
        ),
        caption_encoder=None,
        collection="scenes",
    )

    narrow = await engine.search("rainy day without people", limit=10, mode="siglip")
    widened = await engine.search("rainy day without people", limit=10, mode="siglip", exclude=[])

    assert [match.keyframe.video_id for match in narrow.matches] == ["video-b"]
    assert {match.keyframe.video_id for match in widened.matches} == {"video-a", "video-b"}
    assert narrow.exhaustive is False


# -- completeness ------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_matching_video_is_counted_not_just_the_page() -> None:
    """The training-set requirement: the total is the corpus answer, not the page.

    A caller sizing a dataset needs to know that 40 videos match even when 5 are
    on screen, and needs a cursor to reach the rest.
    """

    points = [
        keyframe(f"p{index}", f"video-{index}", "Snow covers the road.", timestamp=1.0)
        for index in range(40)
    ]
    outcome = await build_engine(points).search("snowy day", limit=5)

    assert len(outcome.matches) == 5
    assert outcome.total_videos == 40
    assert outcome.exhaustive is True
    assert outcome.next_cursor is not None


@pytest.mark.asyncio
async def test_completeness_does_not_depend_on_the_ann_pool() -> None:
    """A video the vector search never returned still has to be found.

    This is what the caption scan is for. If the ANN pool were the only source of
    candidates, "every snowy video" would silently mean "every snowy video the
    approximate search happened to surface".
    """

    points = [
        keyframe(f"p{index}", f"video-{index}", "Deep snow along the roadside.", timestamp=1.0)
        for index in range(30)
    ]
    # The ANN returns a single point; the other 29 exist only in the caption scan.
    outcome = await build_engine(points, ann=["p0"]).search("snowy day", limit=50)

    assert outcome.total_videos == 30
    assert outcome.exhaustive is True


@pytest.mark.asyncio
async def test_a_query_with_no_known_concept_is_not_claimed_to_be_complete() -> None:
    points = [keyframe("p1", "video-a", "A road stretches into the distance.", timestamp=1.0)]
    outcome = await build_engine(points).search("brutalist concrete geometry", limit=10)

    assert outcome.exhaustive is False
    assert "caption_text" not in outcome.signals_used


# -- the similarity floor ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_subject_the_corpus_lacks_returns_nothing() -> None:
    """The failure this floor exists to stop.

    Nearest-neighbour search always has neighbours to return, so without a floor
    a query for a subject the corpus does not contain comes back as the whole
    corpus ranked by how little it resembles the query -- "spiderman" answered
    with several hundred dashcam clips, with nothing to indicate the answer is
    junk.
    """

    points = [
        keyframe(f"p{index}", f"video-{index}", "A car drives along a dual carriageway.")
        for index in range(5)
    ]
    scores = {f"p{index}": 0.01 for index in range(5)}
    outcome = await build_engine(points, scores=scores).search("spiderman", limit=10)

    assert outcome.matches == ()
    assert outcome.total_videos == 0
    # The distinction the UI needs: not "no match", but "nothing of the kind here".
    assert outcome.below_threshold is True
    assert outcome.similarity_floor == pytest.approx(0.09)


@pytest.mark.asyncio
async def test_qwen_cannot_override_a_siglip_out_of_domain_verdict() -> None:
    """Hybrid used to fill the page with Qwen neighbours of rubbish queries.

    SigLIP's 0.09 floor correctly rejects "spiderman"; Qwen's 0.02 floor does
    not. Letting Qwen contribute after SigLIP found nothing turned an honest
    empty answer into several hundred dashcam clips.
    """

    points = [
        keyframe(f"p{index}", f"video-{index}", "A car drives along a dual carriageway.")
        for index in range(5)
    ]
    client = FakeQdrant(
        points,
        scores_by_vector={
            "siglip": {f"p{index}": 0.01 for index in range(5)},
            "qwen": {f"p{index}": 0.4 for index in range(5)},
        },
    )
    engine = SceneSearchEngine(
        client=client,
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )

    hybrid = await engine.search("spiderman", limit=10, mode="hybrid")

    assert hybrid.matches == ()
    assert hybrid.below_threshold is True
    assert "qwen" not in hybrid.signals_used


@pytest.mark.asyncio
async def test_candidates_above_the_floor_still_come_back() -> None:
    points = [
        keyframe("near", "video-a", "A tunnel lit by orange lamps."),
        keyframe("far", "video-b", "A car drives along a dual carriageway."),
    ]
    outcome = await build_engine(
        points, ann=["near", "far"], scores={"near": 0.14, "far": 0.01}
    ).search("a tunnel", limit=10, mode="hybrid")

    assert [match.keyframe.point_id for match in outcome.matches] == ["near"]
    assert outcome.below_threshold is False


@pytest.mark.asyncio
async def test_the_floor_reaches_qdrant_rather_than_being_applied_after() -> None:
    points = [keyframe("p1", "video-a", "Snow on the road.")]
    client = FakeQdrant(points)
    engine = SceneSearchEngine(
        client=client,
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )
    await engine.search("snowy day", limit=5, mode="hybrid")

    assert [query.get("score_threshold") for query in client.queries] == [
        pytest.approx(0.09),
        pytest.approx(0.02),
    ]
    assert [query["using"] for query in client.queries] == [
        "siglip",
        "qwen",
    ]


@pytest.mark.asyncio
async def test_a_caption_match_is_not_held_to_the_similarity_floor() -> None:
    """Caption evidence outranks the cosine that failed to find it.

    A caption that says snow covers the road is direct evidence, and discarding
    it because the image embedding scored poorly would break the completeness
    promise for exactly the videos the vector search is worst at.
    """

    points = [keyframe("p1", "video-a", "Thick snow covers the road and the parked cars.")]
    outcome = await build_engine(points, scores={"p1": 0.01}).search("snowy day", limit=10)

    assert [match.keyframe.video_id for match in outcome.matches] == ["video-a"]
    assert "caption_text" in outcome.signals_used
    assert "visual" not in outcome.signals_used


@pytest.mark.asyncio
async def test_min_score_can_tighten_the_floor_but_not_lower_it() -> None:
    # A query with no known concept, so the vector tower is the only signal and
    # the floor is the only thing deciding.
    points = [keyframe("p1", "video-a", "A row of shops behind iron railings.")]

    # Explicitly asking for no cutoff must not defeat the calibrated one. The
    # request field defaults to zero, so honouring it downward would disable the
    # floor for every caller that never sets it.
    permissive = await build_engine(points, scores={"p1": 0.01}).search(
        "brutalist concrete geometry", limit=10, min_score=0.0
    )
    assert permissive.matches == ()

    strict_request = await build_engine(points, scores={"p1": 0.12}).search(
        "brutalist concrete geometry", limit=10, min_score=0.3
    )
    assert strict_request.matches == ()


# -- concepts are hard filters ------------------------------------------------


@pytest.mark.asyncio
async def test_a_caption_silent_on_a_required_concept_is_rejected() -> None:
    """A query for "snowy day" must not return a frame nothing says is snowy.

    The vector search will happily rank a bright overcast road highly for "snowy
    day". Admitting it because the caption merely fails to contradict it produces
    a result the user reads as a broken filter, and there is no way for them to
    tell it apart from one.
    """

    points = [
        keyframe("silent", "video-a", "A car drives past a row of shops in daylight."),
        keyframe("snowy", "video-b", "Snow covers the road and the parked cars."),
    ]
    outcome = await build_engine(points, ann=["silent", "snowy"]).search("snowy day", limit=10)

    assert [match.keyframe.video_id for match in outcome.matches] == ["video-b"]
    assert outcome.matches[0].confirmed == ("snow",)


@pytest.mark.asyncio
async def test_relaxing_strictness_admits_the_silent_caption() -> None:
    points = [
        keyframe("silent", "video-a", "A car drives past a row of shops in daylight."),
        keyframe("snowy", "video-b", "Snow covers the road and the parked cars."),
    ]
    engine = build_engine(points, ann=["silent", "snowy"])

    hard = await engine.search("snowy day", limit=10)
    soft = await engine.search("snowy day", limit=10, strict=False)

    assert hard.total_videos == 1
    assert soft.total_videos == 2


@pytest.mark.asyncio
async def test_a_concept_no_caption_confirms_is_named() -> None:
    """Names the word to remove, rather than reporting a bare empty result."""

    points = [keyframe("p1", "video-a", "A car drives along a dual carriageway.")]
    outcome = await build_engine(points, scores={"p1": 0.02}).search("snowy day", limit=10)

    assert outcome.matches == ()
    assert outcome.unconfirmed_concepts == ("snow",)


# -- renderable results ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_video_is_represented_by_a_keyframe_that_can_be_rendered() -> None:
    """Two in five keyframes have no derived media, so score alone is not enough.

    Both candidates satisfy the query, so choosing the one that can draw an image
    and open a player costs a slightly lower-ranked moment and gains a result the
    user can actually judge.
    """

    points = [
        keyframe("best-but-blank", "video-a", "Snow on the road.", thumbnail=False, video=False),
        keyframe("renderable", "video-a", "Snow on the road here too.", timestamp=6.0),
    ]
    outcome = await build_engine(points, ann=["best-but-blank", "renderable"]).search(
        "snowy day", limit=10
    )

    assert [match.keyframe.point_id for match in outcome.matches] == ["renderable"]
    # The video is still reported as having both matching moments.
    assert outcome.matches[0].keyframes_matched == 2


@pytest.mark.asyncio
async def test_a_video_with_no_renderable_keyframe_is_still_returned() -> None:
    """Dropping it would understate the corpus, which is the number being sized."""

    points = [
        keyframe("blank", "video-a", "Snow on the road.", thumbnail=False, video=False),
    ]
    outcome = await build_engine(points).search("snowy day", limit=10)

    assert [match.keyframe.video_id for match in outcome.matches] == ["video-a"]
    assert outcome.matches[0].keyframe.renderable is False


@pytest.mark.asyncio
async def test_a_thumbnail_without_a_clip_does_not_count_as_renderable() -> None:
    points = [
        keyframe("image-only", "video-a", "Snow on the road.", video=False),
        keyframe("complete", "video-a", "Snow here as well.", timestamp=6.0),
    ]
    outcome = await build_engine(points, ann=["image-only", "complete"]).search(
        "snowy day", limit=10
    )

    assert [match.keyframe.point_id for match in outcome.matches] == ["complete"]


# -- pagination --------------------------------------------------------------


@pytest.mark.asyncio
async def test_pages_do_not_overlap_and_end_cleanly() -> None:
    points = [
        keyframe(f"p{index}", f"video-{index}", "Snow on the road.", timestamp=1.0)
        for index in range(12)
    ]
    engine = build_engine(points)

    first = await engine.search("snowy day", limit=5)
    second = await engine.search("snowy day", limit=5, cursor=first.next_cursor)
    third = await engine.search("snowy day", limit=5, cursor=second.next_cursor)

    seen = [[match.keyframe.video_id for match in page.matches] for page in (first, second, third)]
    flat = [video for page in seen for video in page]
    assert len(flat) == len(set(flat)) == 12
    assert third.next_cursor is None


@pytest.mark.asyncio
async def test_a_cursor_from_another_query_is_rejected() -> None:
    from search.cursor import CursorError

    points = [
        keyframe(f"p{index}", f"video-{index}", "Snow on the road.", timestamp=1.0)
        for index in range(12)
    ]
    engine = build_engine(points)
    first = await engine.search("snowy day", limit=5)

    with pytest.raises(CursorError):
        await engine.search("rainy day", limit=5, cursor=first.next_cursor)


# -- signals -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_visual_mode_skips_the_caption_vector_query() -> None:
    points = [keyframe("p1", "video-a", "Snow on the road.", timestamp=1.0)]
    engine = build_engine(points)

    outcome = await engine.search("snowy day", limit=5, mode="visual")

    assert "visual" in outcome.signals_used
    assert "caption_vector" not in outcome.signals_used


@pytest.mark.asyncio
async def test_the_named_vector_is_the_one_the_index_uses() -> None:
    """Guards the silent-failure case.

    Querying the wrong named vector, or a vector name that does not exist, does
    not raise anything a user would see -- it returns confidently ranked nonsense.
    """

    points = [keyframe("p1", "video-a", "Snow on the road.", timestamp=1.0)]
    client = FakeQdrant(points)
    engine = SceneSearchEngine(
        client=client,
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )
    await engine.search("snowy day", limit=5, mode="hybrid")

    assert [query["using"] for query in client.queries] == [
        "siglip",
        "qwen",
    ]


@pytest.mark.asyncio
async def test_explain_reports_which_signal_carried_a_result() -> None:
    points = [keyframe("p1", "video-a", "Snow on the road.", timestamp=1.0)]
    outcome = await build_engine(points).search("snowy day", limit=5, explain=True, mode="hybrid")

    assert set(outcome.matches[0].signals) <= {
        "qwen",
        "visual",
        "caption_vector",
        "caption_text",
        "rerank",
    }
    assert outcome.matches[0].signals


@pytest.mark.asyncio
async def test_search_mode_matches_the_schema_literal() -> None:
    from typing import get_args

    from schemas.search import SearchMode as SchemaMode
    from search.engine import SearchMode as EngineMode

    assert set(get_args(SchemaMode)) == set(get_args(EngineMode))


@pytest.mark.asyncio
async def test_search_modes_qwen_siglip_hybrid() -> None:
    points = [keyframe("p1", "video-a", "A red car on the highway.")]
    client = FakeQdrant(points)
    engine = SceneSearchEngine(
        client=client,
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )

    client.queries.clear()
    await engine.search("red car", mode="qwen")
    assert [q["using"] for q in client.queries] == ["qwen"]

    client.queries.clear()
    await engine.search("red car", mode="siglip")
    assert [q["using"] for q in client.queries] == ["siglip"]

    client.queries.clear()
    await engine.search("red car", mode="hybrid")
    queries_using = {q["using"] for q in client.queries}
    assert queries_using == {"qwen", "siglip"}


# -- the snapshot a request reads must not move underneath it -----------------


@pytest.mark.asyncio
async def test_a_reload_during_concept_resolution_cannot_misalign_the_arrays() -> None:
    # The failure this prevents is not an error: the concept arrays stay indexed
    # by the OLD frame positions while the engine reads the NEW frame tuple, so a
    # query for "snowy day" returns sunny frames, each reporting confirmed=["snow"],
    # with exhaustive=true attached. A confidently wrong, complete-looking answer.
    from search.catalog import KeyframeCatalog

    catalog = KeyframeCatalog()
    small = [keyframe("p0", "video-0", "Deep snow covers the road.", timestamp=1.0)]
    big = [
        keyframe(f"q{i}", f"video-{i}", "A dry road in bright sunlight.", timestamp=1.0)
        for i in range(12)
    ]

    await catalog.ensure_loaded(FakeQdrant(small))
    view = catalog.view()
    # A reload lands between pinning the view and using the arrays.
    await catalog.ensure_loaded(FakeQdrant(big), force=True)

    arrays = await catalog.concept_arrays(view, ("snow",))
    # Aligned to the view that was pinned, not to whatever the catalog holds now.
    assert len(arrays["snow"][0]) == len(view.frames) == 1
    # And the stale arrays were not cached against the new generation.
    fresh = await catalog.concept_arrays(catalog.view(), ("snow",))
    assert len(fresh["snow"][0]) == 12
    assert "present" not in fresh["snow"][0], "sunny captions must not confirm snow"


@pytest.mark.asyncio
async def test_a_snapshot_behind_the_collection_withdraws_the_completeness_claim() -> None:
    # `exhaustive` promises every keyframe in the corpus was checked. Candidates
    # the snapshot has never seen are direct evidence that it was not.
    points = [keyframe("p1", "video-a", "A snowy road at night.", timestamp=1.0)]
    engine = build_engine(points)
    engine._client._ann = ["p1", "not-in-catalog-1", "not-in-catalog-2"]  # noqa: SLF001
    engine._client._points = [*points]  # noqa: SLF001

    outcome = await engine.search("snowy day", limit=10)
    assert outcome.stale_candidates == 2
    assert outcome.exhaustive is False


@pytest.mark.asyncio
async def test_a_tower_outage_is_not_reported_as_an_authoritative_empty_answer() -> None:
    # Without this, a total Qdrant outage returns 0 results with exhaustive=true
    # and below_threshold=false — indistinguishable from "the corpus contains
    # nothing like this".
    class Broken(FakeQdrant):
        async def query_points(self, **kwargs: Any) -> FakeResponse:
            raise RuntimeError("qdrant is unreachable")

    engine = SceneSearchEngine(
        client=Broken([keyframe("p1", "video-a", "A dry road.", timestamp=1.0)]),
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )
    outcome = await engine.search("snowy day", limit=10)
    assert outcome.degraded is True
    assert outcome.exhaustive is False


@pytest.mark.asyncio
async def test_an_absent_optional_caption_tower_is_not_degradation() -> None:
    # sentence-transformers is optional and a deployment without it is supported.
    # Treating absence as an error would drop the completeness claim on every
    # search of the default install.
    points = [keyframe("p1", "video-a", "A snowy road at night.", timestamp=1.0)]
    outcome = await build_engine(points).search("snowy day", limit=10)
    assert outcome.degraded is False
    assert outcome.exhaustive is True


# -- an empty answer must name the right reason -------------------------------


@pytest.mark.asyncio
async def test_below_threshold_is_not_set_while_results_are_being_returned() -> None:
    # The caption scan is exempt from the similarity floor by design, so a concept
    # query can return real results while every cosine fell short. Reporting
    # below_threshold there makes the UI print "nothing of the kind here" above
    # two valid results.
    points = [
        keyframe("p1", "video-a", "Deep snow covers the road.", timestamp=1.0),
        keyframe("p2", "video-b", "A snowy street at night.", timestamp=2.0),
    ]
    engine = build_engine(points, scores={"p1": 0.01, "p2": 0.01})
    outcome = await engine.search("snowy day", limit=10)

    assert outcome.matches, "the caption scan should still answer this"
    assert outcome.below_threshold is False


# -- ablations must isolate the signal they name ------------------------------


@pytest.mark.asyncio
async def test_visual_mode_does_not_smuggle_in_the_caption_scan() -> None:
    # The modes exist so the contribution of each tower can be measured. A
    # "visual only" run that includes the caption scan overstates the visual tower
    # by whatever the scan contributed, and every ablation number built on it.
    points = [keyframe("p1", "video-a", "Deep snow covers the road.", timestamp=1.0)]
    engine = build_engine(points, scores={"p1": 0.01})  # below the floor
    outcome = await engine.search("snowy day", limit=10, mode="visual")

    assert "caption_text" not in outcome.signals_used
    assert outcome.matches == ()


# -- pagination must not silently duplicate or skip ---------------------------


@pytest.mark.asyncio
async def test_a_cursor_from_a_different_filter_set_is_rejected() -> None:
    # Reproduced before the fix: changing `require` between pages skipped two
    # videos the user never saw; changing `min_score` returned two they already
    # had. Both cursors were accepted silently.
    from search.cursor import CursorError

    points = [
        keyframe(f"p{i}", f"video-{i}", "A snowy road at night.", timestamp=float(i))
        for i in range(8)
    ]
    engine = build_engine(points)

    first = await engine.search("snowy day", limit=2)
    assert first.next_cursor

    for kwargs in (
        {"require": ["night"]},
        {"video_ids": ["video-1"]},
        {"min_score": 0.5},
        {"strict": False},
        {"limit": 5},
    ):
        with pytest.raises(CursorError):
            await engine.search("snowy day", cursor=first.next_cursor, **kwargs)


@pytest.mark.asyncio
async def test_a_cursor_minted_before_a_reload_is_rejected_rather_than_mispaging() -> None:
    # A reload re-ranks everything: fused scores shift and a video's representative
    # keyframe can change, so the (score, id) the cursor resumes from no longer
    # identifies the same position. Before this, one video appeared on two pages
    # and two were unreachable — on a seven-keyframe corpus.
    from search.catalog import KeyframeCatalog
    from search.cursor import CursorError

    points = [
        keyframe(f"p{i}", f"video-{i}", "A snowy road at night.", timestamp=float(i))
        for i in range(6)
    ]
    catalog = KeyframeCatalog()
    engine = SceneSearchEngine(
        client=FakeQdrant(points),
        catalog=catalog,
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )

    first = await engine.search("snowy day", limit=2)
    assert first.next_cursor

    await catalog.ensure_loaded(FakeQdrant(points), force=True)  # the TTL expires

    with pytest.raises(CursorError):
        await engine.search("snowy day", cursor=first.next_cursor, limit=2)


@pytest.mark.asyncio
async def test_paging_the_same_search_still_works() -> None:
    # The fingerprint got much stricter; this pins that it did not become so
    # strict that ordinary pagination breaks.
    points = [
        keyframe(f"p{i}", f"video-{i}", "A snowy road at night.", timestamp=float(i))
        for i in range(6)
    ]
    engine = build_engine(points)

    first = await engine.search("snowy day", limit=2)
    second = await engine.search("snowy day", limit=2, cursor=first.next_cursor)

    seen_first = {m.keyframe.video_id for m in first.matches}
    seen_second = {m.keyframe.video_id for m in second.matches}
    assert len(seen_first) == 2
    assert seen_first.isdisjoint(seen_second), "a video must not appear on two pages"


# -- the moment, and the clip it came from ------------------------------------


@pytest.mark.asyncio
async def test_a_result_reports_how_many_moments_of_its_clip_contradict_the_query() -> None:
    # The MVP question this exists for. "Rainy day with no pedestrians" returns the
    # moment that has none; the rest of that 40-second clip may well show one. A
    # user told "clean at 0:12 — 2 other moments mention people" understands the
    # tool. A user who finds out by watching concludes the search is broken.
    points = [
        keyframe("p1", "video-a", "Heavy rain on an empty street, no pedestrians.", timestamp=1.0),
        keyframe("p2", "video-a", "Rain falls as two pedestrians cross.", timestamp=8.0),
        keyframe("p3", "video-a", "A pedestrian waits in the rain.", timestamp=20.0),
        keyframe("p4", "video-b", "Rain on a quiet road, nobody about.", timestamp=2.0),
    ]
    outcome = await build_engine(points).search("rainy day without people", limit=10)

    by_video = {m.keyframe.video_id: m for m in outcome.matches}
    assert "video-a" in by_video, "the clean moment inside the busy clip is a correct result"
    assert by_video["video-a"].contradicting_moments == 2
    assert by_video["video-a"].keyframes_in_video == 3
    # A clip with no contradicting moment reports zero rather than nothing.
    assert by_video["video-b"].contradicting_moments == 0


def huy_keyframe(
    point_id: str,
    video_id: str,
    *,
    caption: str = "",
    people: list[str] | None = None,
    vehicles: list[str] | None = None,
    weather: str | None = "sunny",
    time_of_day: str = "daytime",
    road_condition: str = "dry",
    ocr: str = "",
    timestamp: float = 1.0,
) -> FakePoint:
    payload: dict[str, object] = {
        "video_id": video_id,
        "timestamp_sec": timestamp,
        "frame_no": int(timestamp * 30),
        "caption": caption,
        "environment": {
            "weather": weather,
            "time_of_day": time_of_day,
            "road_condition": road_condition,
        },
        "ocr": ocr,
        "minio_thumbnail_key": f"thumbnails/{video_id}/{point_id}.jpg",
        "minio_video_key": f"videos/{video_id}.mov",
    }
    if people is not None:
        payload["people"] = people
    if vehicles is not None:
        payload["vehicles"] = vehicles
    return FakePoint(id=point_id, payload=payload)


@pytest.mark.asyncio
async def test_huy_payload_sunny_street_matches_clear_weather() -> None:
    points = [
        huy_keyframe(
            "p1",
            "video-a",
            caption="A tree-lined residential street.",
            people=["pedestrian in red shirt crossing the road"],
            vehicles=["black suv", "white sedan"],
            ocr="BROOKLYN",
        )
    ]
    outcome = await build_engine(points).search("sunny residential street", limit=10)
    assert [m.keyframe.video_id for m in outcome.matches] == ["video-a"]
    assert "clear_sky" in outcome.matches[0].confirmed
    assert "residential" in outcome.matches[0].confirmed


@pytest.mark.asyncio
async def test_a_caption_beats_an_empty_structured_list_when_they_disagree() -> None:
    # An empty `people: []` is ambiguous. When it contradicts a caption that
    # positively describes people, the caption wins: "without people" must reject
    # this frame rather than return it with a false claim of absence.
    points = [
        huy_keyframe(
            "p1",
            "video-a",
            caption="A sunny street with several pedestrians crossing.",
            people=[],
        )
    ]
    outcome = await build_engine(points).search("sunny day without people", limit=10)
    assert outcome.matches == ()


@pytest.mark.asyncio
async def test_an_empty_structured_list_still_proves_absence_when_the_caption_is_silent() -> None:
    points = [
        huy_keyframe(
            "p1",
            "video-a",
            caption="A sunny street with parked cars along the kerb.",
            people=[],
        )
    ]
    outcome = await build_engine(points).search("sunny day without people", limit=10)
    assert [m.keyframe.point_id for m in outcome.matches] == ["p1"]
    assert outcome.matches[0].denied == ("people",)


@pytest.mark.asyncio
async def test_a_disagreement_is_counted_so_the_extractor_semantics_can_be_measured() -> None:
    from search.catalog import _resolve_concepts, keyframe_from_payload
    from search.query import split_clauses

    frames = tuple(
        frame
        for frame in (
            keyframe_from_payload(
                point.id,
                point.payload,  # type: ignore[arg-type]
            )
            for point in (
                huy_keyframe(
                    "p1", "video-a", caption="Several pedestrians crossing the road.", people=[]
                ),
                huy_keyframe(
                    "p2", "video-b", caption="An empty road with no one about.", people=[]
                ),
            )
        )
        if frame is not None
    )
    clauses = tuple(split_clauses(frame.caption) for frame in frames)
    polarities, _ = _resolve_concepts(frames, clauses, ("people",))["people"]
    assert polarities == ("present", "absent")


@pytest.mark.asyncio
async def test_huy_people_list_rejects_without_people() -> None:
    points = [
        huy_keyframe(
            "busy",
            "video-a",
            caption="A sunny residential street.",
            people=["person standing on the sidewalk"],
        ),
        huy_keyframe(
            "clean",
            "video-b",
            caption="A sunny residential street.",
            people=[],
        ),
    ]
    outcome = await build_engine(points).search("sunny day without people", limit=10)
    assert [m.keyframe.point_id for m in outcome.matches] == ["clean"]


@pytest.mark.asyncio
async def test_huy_sunny_is_not_a_rainy_day() -> None:
    points = [
        huy_keyframe("p1", "video-a", caption="A tree-lined street.", people=[]),
    ]
    outcome = await build_engine(points).search("rainy day", limit=10)
    assert outcome.matches == ()
    assert "rain" in outcome.unconfirmed_concepts


@pytest.mark.asyncio
async def test_huy_ocr_query_finds_the_frame_without_a_lexicon_concept() -> None:
    points = [
        huy_keyframe("p1", "video-a", caption="A residential street.", people=[], ocr="BROOKLYN"),
        huy_keyframe("p2", "video-b", caption="A residential street.", people=[], ocr="QUEENS"),
    ]
    catalog = KeyframeCatalog()
    engine = SceneSearchEngine(
        client=FakeQdrant(points),
        catalog=catalog,
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )
    outcome = await engine.search("BROOKLYN", limit=10)
    assert [m.keyframe.point_id for m in outcome.matches] == ["p1"]
    assert catalog.view().ocr_by_value == {"brooklyn": "BROOKLYN", "queens": "QUEENS"}


@pytest.mark.asyncio
async def test_strict_concepts_stay_on_when_any_frame_has_a_caption() -> None:
    """A captionless neighbour must not disable filters for captioned frames."""

    points = [
        keyframe("captioned", "video-a", "A sunny residential street."),
        visual_keyframe("blank", "video-b"),
        keyframe("rain", "video-c", "Heavy rain on the road."),
    ]
    outcome = await build_engine(points, ann=["blank", "captioned", "rain"]).search(
        "rainy day", limit=10
    )
    assert [m.keyframe.video_id for m in outcome.matches] == ["video-c"]


@pytest.mark.asyncio
async def test_captionless_structured_fields_still_filter_required_concepts() -> None:
    points = [
        huy_keyframe("sunny", "video-a", caption="", weather="sunny", people=[]),
        huy_keyframe("rain", "video-b", caption="", weather="rainy", people=[]),
    ]
    outcome = await build_engine(points).search("rainy day", limit=10)
    assert [m.keyframe.video_id for m in outcome.matches] == ["video-b"]


@pytest.mark.asyncio
async def test_huy_vehicle_phrases_satisfy_a_car_query() -> None:
    points = [
        huy_keyframe(
            "p1",
            "video-a",
            caption="A residential street.",
            people=[],
            vehicles=["black suv", "white sedan"],
        )
    ]
    outcome = await build_engine(points).search("cars on a sunny street", limit=10)
    assert [m.keyframe.video_id for m in outcome.matches] == ["video-a"]
    assert "car" in outcome.matches[0].confirmed


@pytest.mark.asyncio
async def test_a_query_with_no_exclusions_reports_no_contradictions() -> None:
    points = [keyframe("p1", "video-a", "A snowy road at night.", timestamp=1.0)]
    outcome = await build_engine(points).search("snowy day", limit=10)
    assert outcome.matches[0].contradicting_moments == 0
