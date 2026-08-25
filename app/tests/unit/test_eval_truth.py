"""Ground truth, the circularity guard, and the MOT reader.

The test that matters most here is the one asserting the harness *refuses* to
score caption-derived truth against caption-driven retrieval. That refusal is the
difference between a measurement and a tautology, and unlike a wrong number it
leaves no trace in the output when it is missing.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from eval.mot import (
    MotFormatError,
    ObjectTruth,
    TracksUnavailable,
    normalise_class,
    parse_frame_name,
    read_mot_csv,
    read_mot_tracks,
)
from eval.truth import (
    BehaviorGroundTruth,
    CircularEvaluationError,
    FixtureGroundTruth,
    GroundTruthUnavailable,
    HumanGroundTruth,
    MotGroundTruth,
    ResultRef,
    Source,
    all_of,
    at_least,
    check_independence,
    none_of,
)

# -- the guard ---------------------------------------------------------------


class _CaptionTruth:
    source = Source.CAPTIONS

    def judge(self, query_id: str, results: object) -> object:  # pragma: no cover
        raise AssertionError("must never be reached")


def test_caption_truth_against_caption_retrieval_is_refused() -> None:
    with pytest.raises(CircularEvaluationError, match="FR-EVAL-06"):
        check_independence(_CaptionTruth(), ["visual", "caption_text"], query_id="att-rain")


def test_caption_truth_against_the_visual_tower_alone_is_allowed() -> None:
    # Not circular: the image embedding never read the caption. Narrow, but real,
    # and refusing it would be superstition rather than rigour.
    check_independence(_CaptionTruth(), ["visual"], query_id="att-rain")


def test_mot_truth_is_never_refused() -> None:
    truth = MotGroundTruth(truth=ObjectTruth(), predicates={})
    check_independence(truth, ["visual", "caption_text", "caption_vector"])


# -- reading the label table -------------------------------------------------


def test_frame_names_split_on_the_last_hyphen() -> None:
    # The video id contains hyphens of its own, so splitting from the left loses
    # half the identifier and every join then misses.
    key = parse_frame_name("01c71072-718028b8-0000001.jpg")
    assert key is not None
    assert (key.video_id, key.frame_no) == ("01c71072-718028b8", 1)


def test_an_unrecognised_filename_is_reported_not_guessed() -> None:
    assert parse_frame_name("frame_1.tiff") is None


def test_class_names_are_mapped_onto_the_query_vocabulary() -> None:
    assert normalise_class("pedestrian") == "person"
    assert normalise_class("Traffic Light") == "traffic_light"
    # Unmapped classes survive rather than vanishing, so coverage stays honest.
    assert normalise_class("stroller") == "stroller"


def _write_csv(path: Path, rows: list[dict[str, object]], header: list[str]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)  # type: ignore[arg-type]
    return path


def test_counts_are_accumulated_per_frame_per_class(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "labels.csv",
        [
            {
                "name": "vid-a-0000001.jpg",
                "class": "pedestrian",
                "x1": 0,
                "y1": 0,
                "x2": 1,
                "y2": 1,
            },
            {
                "name": "vid-a-0000001.jpg",
                "class": "pedestrian",
                "x1": 0,
                "y1": 0,
                "x2": 1,
                "y2": 1,
            },
            {"name": "vid-a-0000001.jpg", "class": "car", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
            {"name": "vid-b-0000004.jpg", "class": "bus", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
        ],
        ["name", "class", "x1", "y1", "x2", "y2"],
    )
    truth = read_mot_csv(path)
    assert truth.at("vid-a", 1) == {"person": 2, "car": 1}
    assert truth.at("vid-b", 4) == {"bus": 1}


def test_a_frame_absent_from_the_table_is_none_not_empty(tmp_path: Path) -> None:
    # The distinction the whole join guard rests on: "no objects here" is
    # evidence, "not in the table" is a gap, and scoring them the same turns a
    # broken join into a plausible-looking zero.
    path = _write_csv(
        tmp_path / "labels.csv",
        [{"name": "vid-a-0000001.jpg", "class": "car"}],
        ["name", "class"],
    )
    truth = read_mot_csv(path)
    assert truth.at("vid-a", 1) == {"car": 1}
    assert truth.at("vid-a", 999) is None


def test_frame_tolerance_matches_a_nearby_labelled_frame(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "labels.csv",
        [{"name": "vid-a-0000010.jpg", "class": "car"}],
        ["name", "class"],
    )
    truth = read_mot_csv(path)
    assert truth.at("vid-a", 12, tolerance=2) == {"car": 1}
    assert truth.at("vid-a", 14, tolerance=2) is None


def test_coverage_reports_how_much_of_the_lookup_landed(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "labels.csv",
        [{"name": "vid-a-0000001.jpg", "class": "car"}],
        ["name", "class"],
    )
    truth = read_mot_csv(path)
    truth.at("vid-a", 1)
    truth.at("vid-z", 1)
    coverage = truth.coverage()
    assert (coverage.hits, coverage.misses) == (1, 1)
    assert coverage.rate == pytest.approx(0.5)
    assert coverage.is_usable is False
    assert "vid-z" in coverage.missed_videos


def test_video_filter_keeps_the_table_to_what_the_index_holds(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "labels.csv",
        [
            {"name": "vid-a-0000001.jpg", "class": "car"},
            {"name": "vid-z-0000001.jpg", "class": "car"},
        ],
        ["name", "class"],
    )
    truth = read_mot_csv(path, video_ids={"vid-a"})
    assert truth.videos == {"vid-a"}


def test_a_missing_class_column_is_a_loud_error(tmp_path: Path) -> None:
    path = _write_csv(tmp_path / "labels.csv", [{"name": "vid-a-1.jpg"}], ["name"])
    with pytest.raises(MotFormatError, match="object-class column"):
        read_mot_csv(path)


def test_a_table_with_no_boxes_cannot_produce_trajectories(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "labels.csv",
        [{"name": "vid-a-0000001.jpg", "class": "pedestrian"}],
        ["name", "class"],
    )
    with pytest.raises(TracksUnavailable, match="bounding-box"):
        read_mot_tracks(path)


# -- judging -----------------------------------------------------------------


def _truth_with(counts: dict[tuple[str, int], dict[str, int]]) -> ObjectTruth:
    from eval.mot import FrameKey

    return ObjectTruth(counts={FrameKey(v, f): c for (v, f), c in counts.items()})


def test_relevance_is_decided_on_the_keyframe_that_was_shown() -> None:
    # video-a qualifies at frame 50 but the search surfaced frame 1, where it does
    # not. What the user clicks is wrong, so this is a miss — even though the
    # video is in the ideal set.
    truth = _truth_with({("video-a", 1): {"person": 0}, ("video-a", 50): {"person": 4}})
    judge = MotGroundTruth(truth=truth, predicates={"q": at_least("person", 3)})

    judgement = judge.judge("q", [ResultRef("video-a", 1)])
    assert judgement.relevant == frozenset()
    assert judgement.ideal_videos == frozenset({"video-a"})
    assert judgement.video_level_hits == frozenset({"video-a"})
    # The diagnostic that says "retrieval found it, keyframe selection lost it".
    assert judgement.keyframe_precision_loss == 1


def test_a_qualifying_keyframe_is_relevant() -> None:
    truth = _truth_with({("video-a", 50): {"person": 4}})
    judge = MotGroundTruth(truth=truth, predicates={"q": at_least("person", 3)})
    assert judge.judge("q", [ResultRef("video-a", 50)]).relevant == frozenset({"video-a"})


def test_a_result_the_table_cannot_answer_is_unjudged_not_wrong() -> None:
    truth = _truth_with({("video-a", 1): {"person": 4}})
    judge = MotGroundTruth(truth=truth, predicates={"q": at_least("person", 3)})
    judgement = judge.judge("q", [ResultRef("video-unknown", 7)])
    assert judgement.unjudged == frozenset({"video-unknown"})
    assert judgement.relevant == frozenset()


def test_the_recall_denominator_is_every_qualifying_video_in_the_table() -> None:
    truth = _truth_with(
        {
            ("video-a", 1): {"person": 4},
            ("video-b", 1): {"person": 4},
            ("video-c", 1): {"person": 1},
        }
    )
    judge = MotGroundTruth(truth=truth, predicates={"q": at_least("person", 3)})
    judgement = judge.judge("q", [ResultRef("video-a", 1)])
    assert judgement.ideal_videos == frozenset({"video-a", "video-b"})
    assert judgement.exhaustive_denominator is True


def test_negation_predicates_read_the_table_not_the_caption() -> None:
    truth = _truth_with({("video-a", 1): {"car": 2}, ("video-b", 1): {}})
    judge = MotGroundTruth(truth=truth, predicates={"q": all_of(none_of("car"), none_of("person"))})
    judgement = judge.judge("q", [ResultRef("video-a", 1), ResultRef("video-b", 1)])
    assert judgement.relevant == frozenset({"video-b"})


def test_a_query_with_no_predicate_is_unavailable_not_zero() -> None:
    judge = MotGroundTruth(truth=ObjectTruth(), predicates={})
    with pytest.raises(GroundTruthUnavailable, match="no object predicate"):
        judge.judge("unknown", [])


# -- behaviour ---------------------------------------------------------------


class _Event:
    def __init__(self, kind: str, start: float, end: float) -> None:
        self.kind, self.ts_start_s, self.ts_end_s = kind, start, end


def test_a_keyframe_inside_a_crossing_is_relevant() -> None:
    judge = BehaviorGroundTruth(
        events_by_video={"video-a": [_Event("pedestrian_crossing_ego_path", 4.0, 6.0)]},
        kinds={"beh": "pedestrian_crossing_ego_path"},
        fps=5.0,
    )
    # frame 25 at 5 fps is t=5.0s, inside the event.
    assert judge.judge("beh", [ResultRef("video-a", 25)]).relevant == frozenset({"video-a"})


def test_a_keyframe_from_the_right_video_at_the_wrong_moment_is_not_relevant() -> None:
    judge = BehaviorGroundTruth(
        events_by_video={"video-a": [_Event("pedestrian_crossing_ego_path", 4.0, 6.0)]},
        kinds={"beh": "pedestrian_crossing_ego_path"},
        fps=5.0,
    )
    judgement = judge.judge("beh", [ResultRef("video-a", 200)])  # t = 40s
    assert judgement.relevant == frozenset()
    assert judgement.video_level_hits == frozenset({"video-a"})


def test_a_different_behaviour_kind_does_not_count() -> None:
    judge = BehaviorGroundTruth(
        events_by_video={"video-a": [_Event("vehicle_cut_in", 4.0, 6.0)]},
        kinds={"beh": "pedestrian_crossing_ego_path"},
        fps=5.0,
    )
    assert judge.judge("beh", [ResultRef("video-a", 25)]).relevant == frozenset()


# -- other sources -----------------------------------------------------------


def test_human_judgement_denominator_is_the_pool_not_the_corpus() -> None:
    # Recall from a judged pool is a weaker claim than recall from an exhaustive
    # table, and the report is required to say which it had.
    judge = HumanGroundTruth(labels={"q": {"video-a": True, "video-b": False}})
    judgement = judge.judge("q", [ResultRef("video-a", 1), ResultRef("video-b", 1)])
    assert judgement.relevant == frozenset({"video-a"})
    assert judgement.exhaustive_denominator is False


def test_an_unjudged_result_is_counted_separately() -> None:
    judge = HumanGroundTruth(labels={"q": {"video-a": True}})
    judgement = judge.judge("q", [ResultRef("video-a", 1), ResultRef("video-new", 1)])
    assert judgement.unjudged == frozenset({"video-new"})


def test_fixture_truth_is_labelled_as_a_fixture() -> None:
    # So a synthetic number can never be mistaken for a measurement of the corpus.
    assert FixtureGroundTruth(relevant_by_query={}).source is Source.FIXTURE
