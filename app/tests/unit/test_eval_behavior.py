"""Behaviour rules over ground-truth tracks.

These rules, not the encoder, are what make the project's headline query
answerable — a single-frame encoder cannot represent a trajectory. So the tests
that matter are the ones separating a genuine crossing from the three things that
look like one: someone standing at the kerb, a vehicle passing in the next lane,
and a track that wobbles across the centre without going anywhere.
"""

from __future__ import annotations

import pytest

from eval.behavior import (
    MIN_TRACK_POINTS,
    Track,
    TrackPoint,
    behavior_kinds,
    detect_behaviors,
    detect_pedestrian_at_curb,
    detect_pedestrian_crossing,
    detect_vehicle_cut_in,
    ego_half_width_at,
    in_ego_path,
)

BOX = 0.03  # half-size of a small synthetic bounding box


def _point(frame: int, x: float, y: float) -> TrackPoint:
    return TrackPoint(
        frame_index=frame,
        ts_s=frame / 5.0,
        x1=x - BOX,
        y1=y - BOX,
        x2=x + BOX,
        y2=y + BOX,
    )


def _track(track_id: str, class_name: str, xs: list[float], y: float = 0.9) -> Track:
    return Track(
        track_id=track_id,
        class_name=class_name,
        points=[_point(i, x, y) for i, x in enumerate(xs)],
    )


# --- geometry ----------------------------------------------------------------


def test_the_ego_path_widens_toward_the_vehicle() -> None:
    # A trapezoid, not a rectangle: the lane occupies more of the frame nearby.
    assert ego_half_width_at(1.0) > ego_half_width_at(0.6)


def test_above_the_horizon_the_lane_is_absent_not_infinitely_narrow() -> None:
    # Returning 0.0 makes containment fail cleanly instead of matching a point
    # exactly on the centreline a hundred metres away.
    assert ego_half_width_at(0.3) == 0.0
    assert in_ego_path(_point(0, 0.5, 0.3)) is False


def test_containment_uses_the_foot_of_the_box_not_its_centre() -> None:
    # Where an object stands on the road plane is its contact point. Using the
    # centre would place a tall pedestrian further down the lane than they are.
    tall = TrackPoint(frame_index=0, ts_s=0.0, x1=0.47, y1=0.30, x2=0.53, y2=0.95)
    assert in_ego_path(tall) is True


def test_a_point_beside_the_lane_is_outside_it() -> None:
    assert in_ego_path(_point(0, 0.05, 0.9)) is False


# --- the positive case -------------------------------------------------------


def test_a_pedestrian_crossing_the_lane_fires() -> None:
    track = _track("t1", "pedestrian", [0.30, 0.40, 0.50, 0.60, 0.70])
    event = detect_pedestrian_crossing(track)
    assert event is not None
    assert event.kind == "pedestrian_crossing_ego_path"
    assert event.confidence > 0.0
    assert event.evidence["points_in_ego_path"] >= 1


def test_the_event_spans_only_the_time_inside_the_lane() -> None:
    # The result is a moment to watch. Timestamps covering the whole track would
    # seek the player to before the pedestrian was ever in shot.
    track = _track("t2", "pedestrian", [0.05, 0.35, 0.50, 0.65, 0.95])
    event = detect_pedestrian_crossing(track)
    assert event is not None
    assert event.ts_start_s > track.points[0].ts_s


def test_class_synonyms_are_accepted() -> None:
    xs = [0.30, 0.40, 0.50, 0.60, 0.70]
    assert detect_pedestrian_crossing(_track("a", "person", xs)) is not None
    assert detect_pedestrian_crossing(_track("b", "PEDESTRIAN", xs)) is not None


# --- the three things that look like crossings but are not --------------------


def test_someone_standing_at_the_kerb_does_not_fire() -> None:
    track = _track("t3", "pedestrian", [0.08, 0.08, 0.09, 0.08, 0.09])
    assert detect_pedestrian_crossing(track) is None


def test_a_vehicle_passing_in_the_next_lane_does_not_fire_as_a_crossing() -> None:
    # Large horizontal movement, never inside the lane ahead.
    track = _track("t4", "car", [0.02, 0.06, 0.10, 0.14, 0.18], y=0.75)
    assert detect_pedestrian_crossing(track) is None


def test_wobbling_across_the_centre_without_travelling_does_not_fire() -> None:
    # Crosses the centreline repeatedly but goes nowhere: jitter, not a crossing.
    track = _track("t5", "pedestrian", [0.49, 0.51, 0.49, 0.51, 0.50])
    assert detect_pedestrian_crossing(track) is None


def test_moving_inside_the_lane_without_crossing_the_centre_does_not_fire() -> None:
    # Walking along the lane, not across it.
    track = _track("t6", "pedestrian", [0.55, 0.62, 0.70, 0.78, 0.85])
    assert detect_pedestrian_crossing(track) is None


def test_a_track_too_short_to_be_a_trajectory_does_not_fire() -> None:
    track = _track("t7", "pedestrian", [0.30, 0.70][: MIN_TRACK_POINTS - 1])
    assert detect_pedestrian_crossing(track) is None


def test_a_car_is_not_a_pedestrian_crossing() -> None:
    assert detect_pedestrian_crossing(_track("t8", "car", [0.3, 0.5, 0.7])) is None


# --- other rules -------------------------------------------------------------


def test_a_pedestrian_beside_the_lane_is_reported_as_at_curb() -> None:
    # Useful as a negative during evaluation: many of these and few crossings
    # suggests the crossing threshold is too strict.
    # x=0.10 at y=0.9: the trapezoid's half-width there is ~0.31, so 0.20 would
    # actually be *inside* the lane. Standing at the kerb means further out.
    track = _track("t9", "pedestrian", [0.10, 0.11, 0.10, 0.12])
    event = detect_pedestrian_at_curb(track)
    assert event is not None and event.kind == "pedestrian_at_curb"


def test_a_crossing_pedestrian_is_not_also_at_the_curb() -> None:
    track = _track("t10", "pedestrian", [0.30, 0.40, 0.50, 0.60, 0.70])
    assert detect_pedestrian_at_curb(track) is None


def test_a_vehicle_entering_the_lane_is_a_cut_in() -> None:
    track = _track("t11", "car", [0.15, 0.25, 0.38, 0.48, 0.50], y=0.9)
    event = detect_vehicle_cut_in(track)
    assert event is not None and event.kind == "vehicle_cut_in"


def test_a_lead_vehicle_already_in_the_lane_is_not_a_cut_in() -> None:
    track = _track("t12", "car", [0.50, 0.50, 0.51, 0.49], y=0.9)
    assert detect_vehicle_cut_in(track) is None


# --- aggregation -------------------------------------------------------------


def test_detect_behaviors_is_deterministic() -> None:
    # The evaluation compares runs. Non-deterministic ordering would show up as
    # drift that is not there.
    tracks = [
        _track("b", "pedestrian", [0.30, 0.40, 0.50, 0.60, 0.70]),
        _track("a", "pedestrian", [0.30, 0.40, 0.50, 0.60, 0.70]),
    ]
    assert [e.track_id for e in detect_behaviors(tracks)] == [
        e.track_id for e in detect_behaviors(tracks)
    ]


def test_behavior_kinds_are_sorted_and_deduplicated_for_the_payload() -> None:
    # The Qdrant payload's `behaviors` array must be stable across re-indexing,
    # or payload comparison in tests means nothing.
    events = detect_behaviors(
        [
            _track("a", "pedestrian", [0.30, 0.40, 0.50, 0.60, 0.70]),
            _track("b", "pedestrian", [0.30, 0.40, 0.50, 0.60, 0.70]),
        ]
    )
    kinds = behavior_kinds(events)
    assert kinds == sorted(set(kinds))


def test_low_confidence_events_can_be_filtered_out_of_the_payload() -> None:
    events = detect_behaviors([_track("a", "pedestrian", [0.10, 0.11, 0.10, 0.12])])
    assert behavior_kinds(events, min_confidence=0.9) == []


# --- input validation --------------------------------------------------------


def test_out_of_order_points_are_rejected() -> None:
    # Frame order is assumed everywhere downstream; silently accepting a shuffled
    # track would produce timestamps that run backwards.
    with pytest.raises(ValueError, match="frame order"):
        Track(
            track_id="x",
            class_name="pedestrian",
            points=[_point(5, 0.3, 0.9), _point(1, 0.7, 0.9)],
        )


def test_an_empty_track_is_rejected() -> None:
    with pytest.raises(ValueError, match="no points"):
        Track(track_id="x", class_name="pedestrian", points=[])
