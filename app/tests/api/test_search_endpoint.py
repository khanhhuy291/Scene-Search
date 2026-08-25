"""The search endpoint's response contract.

These assertions are the frontend's contract. Each one corresponds to something
the UI reads directly, so a change here is a change to what renders.
"""

from __future__ import annotations

import pytest

from search.catalog import Keyframe
from search.engine import SearchOutcome, VideoMatch
from search.query import parse_query


def _keyframe(*, thumbnail: bool = True, video_key: bool = True) -> Keyframe:
    return Keyframe(
        point_id="11111111-2222-3333-4444-555555555555",
        video_id="00c17a92-d4803287",
        timestamp_s=18.93,
        frame_no=568,
        caption="A rainy street with no visible pedestrians.",
        thumbnail_key="thumbnails/x/y.jpg" if thumbnail else None,
        video_key="videos/x.mov" if video_key else None,
    )


def _outcome(**overrides: object) -> SearchOutcome:
    match = VideoMatch(
        keyframe=overrides.pop("keyframe", None) or _keyframe(),
        score=0.0271,
        keyframes_matched=25,
        confirmed=("rain",),
        denied=("people",),
        signals={"visual": 0.0164, "caption_text": 0.0107},
    )
    defaults: dict[str, object] = {
        "parsed": parse_query("rainy day without people"),
        "matches": (match,),
        "total_videos": 563,
        "total_keyframes": 2525,
        "exhaustive": True,
        "signals_used": ("visual", "caption_text"),
        "next_cursor": "abc123",
        "took_ms": 164.2,
    }
    defaults.update(overrides)
    return SearchOutcome(**defaults)  # type: ignore[arg-type]


class StubEngine:
    def __init__(self, outcome: SearchOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    async def search(self, query: str, **kwargs: object) -> SearchOutcome:
        self.calls.append({"query": query, **kwargs})
        return self.outcome


@pytest.fixture
def stub_engine(monkeypatch: pytest.MonkeyPatch):
    def install(outcome: SearchOutcome) -> StubEngine:
        engine = StubEngine(outcome)
        monkeypatch.setattr("api.v1.search.get_search_engine", lambda: engine)
        return engine

    return install


@pytest.mark.asyncio
async def test_totals_count_videos_and_keyframes_separately(client, stub_engine) -> None:
    """``total`` describes the list it accompanies.

    Results are one per video, so a total counting keyframes would contradict the
    results and would mislead anyone sizing a training set.
    """

    stub_engine(_outcome())
    response = await client.post("/api/v1/search", json={"query": "rainy day without people"})

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 563
    assert body["total_keyframes"] == 2525
    assert len(body["results"]) == 1


@pytest.mark.asyncio
async def test_interpretation_is_echoed_so_it_can_be_corrected(client, stub_engine) -> None:
    stub_engine(_outcome())
    response = await client.post("/api/v1/search", json={"query": "rainy day without people"})

    body = response.json()
    assert body["interpreted_query"] == "rainy day"
    assert body["required_concepts"] == ["rain"]
    assert body["excluded_concepts"] == ["people"]
    assert body["exhaustive"] is True


@pytest.mark.asyncio
async def test_thumbnail_url_points_at_this_api_not_object_storage(client, stub_engine) -> None:
    """A presigned object-store URL would be unreachable from the browser.

    It would also put a credentialed URL in the page. The proxy path keeps it
    relative and stable.
    """

    stub_engine(_outcome())
    response = await client.post("/api/v1/search", json={"query": "rainy day"})

    result = response.json()["results"][0]
    assert result["thumbnail_url"] == (
        "/api/v1/media/thumbnail/11111111-2222-3333-4444-555555555555"
    )
    assert result["preview_url"] == "/api/v1/media/clip/11111111-2222-3333-4444-555555555555"


@pytest.mark.asyncio
async def test_missing_thumbnail_is_null_rather_than_a_broken_url(client, stub_engine) -> None:
    stub_engine(_outcome(keyframe=_keyframe(thumbnail=False, video_key=False)))
    response = await client.post("/api/v1/search", json={"query": "rainy day"})

    result = response.json()["results"][0]
    assert result["thumbnail_url"] is None
    assert result["preview_url"] is None
    # The caption still arrives, so the card has something to render.
    assert result["caption"]


@pytest.mark.asyncio
async def test_results_are_reported_as_frames_not_segments(client, stub_engine) -> None:
    # The index holds keyframes only. Echoing back "segment" because the request
    # defaulted to one would be a claim the data does not support, and the review
    # flow would store it.
    stub_engine(_outcome())
    response = await client.post("/api/v1/search", json={"query": "rainy day"})

    result = response.json()["results"][0]
    assert result["granularity"] == "frame"
    assert result["ts_end_s"] > result["ts_start_s"]


@pytest.mark.asyncio
async def test_result_carries_the_evidence_the_card_shows(client, stub_engine) -> None:
    stub_engine(_outcome())
    response = await client.post("/api/v1/search", json={"query": "rainy day without people"})

    result = response.json()["results"][0]
    assert result["keyframes_matched"] == 25
    assert result["confirmed"] == ["rain"]
    assert result["denied"] == ["people"]
    assert result["frame_no"] == 568


@pytest.mark.asyncio
async def test_overrides_are_forwarded_so_a_chip_can_be_removed(client, stub_engine) -> None:
    engine = stub_engine(_outcome())
    await client.post(
        "/api/v1/search",
        json={"query": "rainy day without people", "require": ["rain"], "exclude": []},
    )

    # An empty list must survive as an empty list. Collapsing it to None would
    # reinstate the inferred exclusion and the chip would never come off.
    assert engine.calls[0]["exclude"] == []
    assert engine.calls[0]["require"] == ["rain"]


@pytest.mark.asyncio
async def test_structured_filters_and_granularity_are_forwarded(client, stub_engine) -> None:
    engine = stub_engine(_outcome())
    response = await client.post(
        "/api/v1/search",
        json={
            "query": "rainy road",
            "granularity": "segment",
            "filters": {
                "dataset": ["uploads"],
                "weather": ["rain"],
                "objects_all": ["car"],
                "time_range_s": [5, 20],
            },
        },
    )

    assert response.status_code == 200
    assert engine.calls[0]["granularity"] == "segment"
    forwarded = engine.calls[0]["filters"]
    assert forwarded.dataset == ["uploads"]
    assert forwarded.weather == ["rain"]
    assert forwarded.objects_all == ["car"]
    assert forwarded.time_range_s == (5.0, 20.0)
    assert response.json()["filters_applied"]["dataset"] == ["uploads"]


@pytest.mark.asyncio
async def test_an_out_of_corpus_query_is_an_answer_not_a_failure(client, stub_engine) -> None:
    """A 200 with no results, and the reason attached.

    The UI has to phrase "nothing here looks like that" differently from "your
    filters excluded everything", so the cause travels with the empty list rather
    than being guessed at from its length.
    """

    stub_engine(
        _outcome(
            matches=(),
            total_videos=0,
            total_keyframes=0,
            exhaustive=False,
            next_cursor=None,
            similarity_floor=0.09,
            below_threshold=True,
        )
    )
    response = await client.post("/api/v1/search", json={"query": "spiderman"})

    body = response.json()
    assert response.status_code == 200
    assert body["results"] == []
    assert body["below_threshold"] is True
    assert body["similarity_floor"] == 0.09


@pytest.mark.asyncio
async def test_a_concept_nothing_confirms_is_named_in_the_response(client, stub_engine) -> None:
    stub_engine(
        _outcome(matches=(), total_videos=0, next_cursor=None, unconfirmed_concepts=("snow",))
    )
    response = await client.post("/api/v1/search", json={"query": "snowy day"})

    assert response.json()["unconfirmed_concepts"] == ["snow"]


@pytest.mark.asyncio
async def test_a_stale_cursor_is_a_client_error(client, stub_engine, monkeypatch) -> None:
    from search.cursor import CursorError

    class Failing:
        async def search(self, *args: object, **kwargs: object) -> SearchOutcome:
            raise CursorError("cursor belongs to a different query")

    monkeypatch.setattr("api.v1.search.get_search_engine", lambda: Failing())
    response = await client.post(
        "/api/v1/search", json={"query": "rainy day", "cursor": "not-this-query"}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_an_empty_query_is_rejected_before_retrieval(client) -> None:
    response = await client.post("/api/v1/search", json={"query": "   "})
    assert response.status_code == 422
