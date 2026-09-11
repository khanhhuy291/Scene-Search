"""The harness end to end, against a fixture corpus and the real search engine.

This is the part that runs in CI. It needs no index, no tunnel and no label file,
but it is not a mock of the harness — the real :class:`SceneSearchEngine` answers
the queries and the real scorer grades them, so a change that breaks retrieval
shows up here rather than three weeks later against the live index.

The fixture corpus is built so that the captions and the object truth *disagree*
in one specific place, on purpose. A caption says a street is quiet while the
label table records four people in that frame. Any harness that quietly scored
captions against captions would rate that result correct; this one has to mark it
wrong, and the test that pins it is the reason to trust every other number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pytest

from eval.mot import FrameKey, ObjectTruth
from eval.report import compare_to_baseline, to_json, to_markdown
from eval.runner import run_ablations, run_case, run_suite
from eval.suite import BEHAVIOURAL, OBJECT, QueryCase
from eval.truth import MotGroundTruth, ResultRef, Source, at_least, none_of
from search.catalog import KeyframeCatalog
from search.engine import SceneSearchEngine


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
    DEFAULT_SCORE = 0.2

    def __init__(self, points: list[FakePoint], scores: dict[str, float] | None = None) -> None:
        self._points = points
        self._scores = scores or {}

    async def scroll(self, **kwargs: Any) -> tuple[list[FakePoint], None]:
        return list(self._points), None

    async def query_points(self, **kwargs: Any) -> FakeResponse:
        limit = kwargs.get("limit", len(self._points))
        threshold = kwargs.get("score_threshold")
        scored = [
            FakeScored(id=p.id, score=self._scores.get(p.id, self.DEFAULT_SCORE))
            for p in self._points[:limit]
        ]
        if threshold is not None:
            scored = [point for point in scored if point.score >= threshold]
        return FakeResponse(scored)


class FakeEncoder:
    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.fixture(autouse=True)
def pinned_tuning(monkeypatch: pytest.MonkeyPatch):
    from core.config import get_settings

    monkeypatch.setenv("SEARCH_VISUAL_FLOOR", "0.09")
    monkeypatch.setenv("SEARCH_CAPTION_FLOOR", "0.0")
    monkeypatch.setenv("SEARCH_STRICT_CONCEPTS", "true")
    monkeypatch.setenv("SEARCH_AGENTIC_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _keyframe(point_id: str, video_id: str, caption: str, frame_no: int) -> FakePoint:
    return FakePoint(
        id=point_id,
        payload={
            "video_id": video_id,
            "timestamp_sec": frame_no / 5.0,
            "frame_no": frame_no,
            "qwen_caption": caption,
            "minio_thumbnail_key": f"thumbnails/{video_id}/{point_id}.jpg",
            "minio_video_key": f"videos/{video_id}.mov",
        },
    )


# One keyframe per video keeps the arithmetic checkable by hand.
CORPUS = [
    _keyframe("p-a", "video-a", "A busy pavement with several pedestrians waiting.", 10),
    _keyframe("p-b", "video-b", "A crowd of people crossing a city street.", 10),
    # The disagreement. The caption calls it quiet; the table below records four
    # people in this frame. Caption-derived truth would score a hit here.
    _keyframe("p-c", "video-c", "A relatively quiet road with no visible pedestrians.", 10),
    _keyframe("p-d", "video-d", "An empty motorway at night, no traffic at all.", 10),
    _keyframe("p-e", "video-e", "A truck ahead on the highway.", 10),
]

OBJECTS = {
    ("video-a", 10): {"person": 5},
    ("video-b", 10): {"person": 7},
    ("video-c", 10): {"person": 4},  # contradicts its own caption, deliberately
    ("video-d", 10): {},
    ("video-e", 10): {"truck": 1, "car": 2},
}


def _object_truth() -> ObjectTruth:
    return ObjectTruth(counts={FrameKey(v, f): c for (v, f), c in OBJECTS.items()})


def _engine(scores: dict[str, float] | None = None) -> SceneSearchEngine:
    return SceneSearchEngine(
        client=FakeQdrant(CORPUS, scores),
        catalog=KeyframeCatalog(),
        encoder=FakeEncoder(),
        caption_encoder=None,
        collection="scenes",
    )


def _case(case_id: str, query: str, predicate, **kwargs: Any) -> QueryCase:
    return QueryCase(
        id=case_id,
        band=OBJECT,
        query=query,
        truth_source=Source.MOT_TRACKS,
        predicate=predicate,
        **kwargs,
    )


def _judge(cases: list[QueryCase]) -> MotGroundTruth:
    return MotGroundTruth(
        truth=_object_truth(),
        predicates={c.id: c.predicate for c in cases if c.predicate},
        frame_tolerance=2,
    )


# -- the point of the whole harness ------------------------------------------


@pytest.mark.asyncio
async def test_a_result_the_caption_endorses_but_the_labels_contradict_is_scored_wrong() -> None:
    # video-c's caption says "no visible pedestrians"; the label table records four
    # people in that exact frame. A harness that scored captions against captions
    # would rate this result correct. The independent truth has to rate it wrong,
    # and if this test ever passes for the wrong reason every other number in the
    # report is worthless.
    cases = [_case("q-none", "a road without any pedestrians", none_of("person"))]
    judge = _judge(cases)

    # The search does retrieve video-c — its caption is the best textual match for
    # the query in this corpus. That is the point.
    result = await run_case(_engine(), cases[0], judge, limit=10)
    assert result.status == "scored"

    judged = judge.judge("q-none", [ResultRef("video-c", 10)])
    assert judged.relevant == frozenset(), "the labels contradict the caption"

    # video-d has no objects at all; video-e has vehicles but no people. Both
    # genuinely satisfy "no pedestrians"; video-c does not.
    assert judge.ideal_videos("q-none") == frozenset({"video-d", "video-e"})
    assert result.ideal_videos == 2


# -- scoring -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_query_with_matching_labels_scores() -> None:
    cases = [_case("q-people", "a street with several pedestrians", at_least("person", 3))]
    result = await run_case(_engine(), cases[0], _judge(cases), limit=10)

    assert result.status == "scored"
    assert result.returned > 0
    assert result.precision_at_10 > 0
    assert result.ideal_videos == 3  # a, b and c all have >= 3 people


@pytest.mark.asyncio
async def test_recall_uses_the_whole_table_as_its_denominator() -> None:
    cases = [_case("q-people", "pedestrians", at_least("person", 3))]
    result = await run_case(_engine(), cases[0], _judge(cases), limit=10)
    assert result.exhaustive_denominator is True
    assert 0.0 <= result.recall_at_50 <= 1.0


@pytest.mark.asyncio
async def test_latency_is_recorded_per_query() -> None:
    cases = [_case("q-people", "pedestrians", at_least("person", 1))]
    result = await run_case(_engine(), cases[0], _judge(cases), limit=10)
    assert result.took_ms >= 0.0


# -- refusals ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_band_with_no_independent_truth_is_unavailable_not_zero() -> None:
    case = QueryCase(
        id="att-rain", band="attribute", query="a rainy night", truth_source=Source.CAPTIONS
    )
    result = await run_case(_engine(), case, None)

    assert result.status == "unavailable"
    assert math.isnan(result.precision_at_10)
    assert result.reason


@pytest.mark.asyncio
async def test_a_query_without_a_predicate_is_unavailable_not_an_error() -> None:
    case = _case("q-undefined", "anything", at_least("person", 1))
    judge = MotGroundTruth(truth=_object_truth(), predicates={})
    result = await run_case(_engine(), case, judge)
    assert result.status == "unavailable"
    assert "no object predicate" in result.reason


@pytest.mark.asyncio
async def test_a_query_that_raises_is_reported_not_swallowed() -> None:
    class Exploding:
        async def search(self, query: str, **kwargs: Any) -> Any:
            raise RuntimeError("qdrant went away")

    case = _case("q-boom", "anything", at_least("person", 1))
    result = await run_case(Exploding(), case, _judge([case]))
    assert result.status == "error"
    assert "qdrant went away" in result.reason


# -- abstention controls ------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unanswerable_query_passes_when_the_floor_rejects_it() -> None:
    case = _case("neg-x", "spiderman", at_least("__never__", 1), expect_empty=True)
    # Every candidate scores below the calibrated floor, which is what the real
    # index does for an out-of-domain query.
    engine = _engine(scores={p.id: 0.01 for p in CORPUS})
    result = await run_case(engine, case, _judge([case]), limit=10)
    assert result.status == "control_pass"


@pytest.mark.asyncio
async def test_an_unanswerable_query_that_returns_results_fails_the_control() -> None:
    case = _case("neg-x", "spiderman", at_least("__never__", 1), expect_empty=True)
    result = await run_case(_engine(), case, _judge([case]), limit=10)
    assert result.status == "control_fail"
    assert "did not reject" in result.reason


# -- the suite ---------------------------------------------------------------


def _suite() -> list[QueryCase]:
    return [
        _case("q-people", "a street with several pedestrians", at_least("person", 3)),
        _case("q-truck", "a truck on the highway", at_least("truck", 1)),
        _case("q-none", "a road without any pedestrians", none_of("person")),
        QueryCase(
            id="att-rain",
            band="attribute",
            query="a rainy night",
            truth_source=Source.CAPTIONS,
            note="captions supply both sides",
        ),
    ]


@pytest.mark.asyncio
async def test_the_suite_summarises_per_band() -> None:
    cases = _suite()
    report = await run_suite(
        _engine(),
        truth_for={OBJECT: _judge(cases), "attribute": None},
        cases=cases,
        limit=10,
    )
    bands = {band.band: band for band in report.bands}
    assert bands[OBJECT].scored == 3
    assert bands["attribute"].is_available is False
    assert bands["attribute"].reason


@pytest.mark.asyncio
async def test_latency_percentiles_are_reported() -> None:
    cases = _suite()
    report = await run_suite(
        _engine(), truth_for={OBJECT: _judge(cases), "attribute": None}, cases=cases, limit=10
    )
    assert report.latency_p50_ms >= 0.0
    assert report.latency_p95_ms >= report.latency_p50_ms


@pytest.mark.asyncio
async def test_the_join_rate_is_reported_so_a_broken_join_is_visible() -> None:
    cases = _suite()
    report = await run_suite(
        _engine(), truth_for={OBJECT: _judge(cases), "attribute": None}, cases=cases, limit=10
    )
    # Every fixture video is in the table, so nothing should be unjudged.
    assert report.join_rate == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_a_broken_join_shows_as_a_low_rate_not_as_bad_retrieval() -> None:
    # The table describes different videos entirely — the exact shape of a video-id
    # format mismatch between the index and the labels.
    elsewhere = ObjectTruth(counts={FrameKey("other-1", 10): {"person": 9}})
    cases = [_case("q-people", "pedestrians", at_least("person", 3))]
    judge = MotGroundTruth(truth=elsewhere, predicates={"q-people": at_least("person", 3)})

    report = await run_suite(_engine(), truth_for={OBJECT: judge}, cases=cases, limit=10)
    assert report.join_rate == pytest.approx(0.0)
    assert "broken join" in to_markdown(report)


# -- ablations and reporting --------------------------------------------------


@pytest.mark.asyncio
async def test_ablations_run_the_variants_that_exist_and_name_the_ones_that_do_not() -> None:
    cases = _suite()
    results = await run_ablations(
        _engine(), truth_for={OBJECT: _judge(cases), "attribute": None}, cases=cases, limit=10
    )
    by_name = {name: (note, report) for name, note, report in results}

    assert by_name["baseline"][1] is not None
    assert by_name["visual only"][1] is not None
    # Not silently omitted: listed with the reason, so a reader cannot mistake an
    # absent row for a zero.
    assert by_name["rerank"][1] is None
    assert "no reranker" in by_name["rerank"][0]


@pytest.mark.asyncio
async def test_the_report_renders_and_serialises() -> None:
    cases = _suite()
    report = await run_suite(
        _engine(), truth_for={OBJECT: _judge(cases), "attribute": None}, cases=cases, limit=10
    )
    markdown = to_markdown(report)
    assert "## Per band" in markdown
    assert "unavailable" in markdown

    payload = to_json(report)
    assert set(payload["bands"]) >= {OBJECT, "attribute"}  # type: ignore[arg-type]


# -- the CI gate --------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_baseline_is_reported_rather_than_silently_passing(tmp_path) -> None:
    cases = _suite()
    report = await run_suite(_engine(), truth_for={OBJECT: _judge(cases)}, cases=cases, limit=10)
    failures = compare_to_baseline(report, tmp_path / "missing.json")
    assert failures and "no baseline" in failures[0]


@pytest.mark.asyncio
async def test_an_unchanged_run_passes_its_own_baseline(tmp_path) -> None:
    import json

    cases = _suite()
    report = await run_suite(_engine(), truth_for={OBJECT: _judge(cases)}, cases=cases, limit=10)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(to_json(report)), encoding="utf-8")

    assert compare_to_baseline(report, path) == []


@pytest.mark.asyncio
async def test_a_precision_drop_beyond_tolerance_fails(tmp_path) -> None:
    import json

    cases = _suite()
    report = await run_suite(_engine(), truth_for={OBJECT: _judge(cases)}, cases=cases, limit=10)
    payload = to_json(report)
    # Pretend the committed baseline was much better than today's run.
    payload["bands"][OBJECT]["precision_at_10"] = 1.0  # type: ignore[index]
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    failures = compare_to_baseline(report, path)
    assert failures and "precision@10" in failures[0]


@pytest.mark.asyncio
async def test_losing_the_ability_to_measure_a_band_is_itself_a_regression(tmp_path) -> None:
    # The failure most likely to arrive by accident: a renamed payload field or an
    # unmounted label file turns a scored band into an unscored one, and without
    # this the build goes green while the evaluation stops evaluating.
    import json

    cases = _suite()
    scored = await run_suite(_engine(), truth_for={OBJECT: _judge(cases)}, cases=cases, limit=10)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(to_json(scored)), encoding="utf-8")

    blind = await run_suite(_engine(), truth_for={OBJECT: None}, cases=cases, limit=10)
    failures = compare_to_baseline(blind, path)
    assert failures and "now unavailable" in failures[0]


@pytest.mark.asyncio
async def test_a_failed_abstention_control_fails_the_build(tmp_path) -> None:
    import json

    cases = [_case("neg-x", "spiderman", at_least("__never__", 1), expect_empty=True)]
    report = await run_suite(_engine(), truth_for={OBJECT: _judge(cases)}, cases=cases, limit=10)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(to_json(report)), encoding="utf-8")

    failures = compare_to_baseline(report, path)
    assert failures and "abstention control" in failures[0]


# -- the shipped suite --------------------------------------------------------


def test_the_committed_suite_covers_every_band() -> None:
    from eval.suite import BANDS, default_suite

    cases = default_suite()
    assert {case.band for case in cases} == set(BANDS)


def test_every_object_and_compositional_case_has_a_predicate() -> None:
    from eval.suite import COMPOSITIONAL, default_suite

    for case in default_suite():
        if case.band in (OBJECT, COMPOSITIONAL) and not case.expect_empty:
            assert case.predicate is not None, f"{case.id} has no predicate"


def test_every_behavioural_case_names_a_rule_that_exists() -> None:
    # A typo in a behaviour kind would silently score the band zero, which reads
    # as "caption search cannot do trajectories" — the very conclusion the band
    # exists to test. Pinning the names against the rules themselves means the
    # band can only ever score zero for a real reason.
    from eval.behavior import behavior_kinds, detect_behaviors
    from eval.suite import default_suite

    from .test_eval_behavior import _track

    detected = set(
        behavior_kinds(
            detect_behaviors(
                [
                    _track("ped", "pedestrian", [0.30, 0.40, 0.50, 0.60, 0.70]),
                    _track("cyc", "cyclist", [0.30, 0.40, 0.50, 0.60, 0.70]),
                    _track("car", "car", [0.15, 0.25, 0.38, 0.48, 0.50]),
                ]
            )
        )
    )
    for case in default_suite():
        if case.band == BEHAVIOURAL:
            assert case.behavior_kind in detected, (
                f"{case.id} names {case.behavior_kind!r}, which no rule produces"
            )


def test_ids_are_unique_so_the_baseline_comparison_is_meaningful() -> None:
    from eval.suite import default_suite

    ids = [case.id for case in default_suite()]
    assert len(ids) == len(set(ids))
