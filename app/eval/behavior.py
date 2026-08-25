"""Behaviour rules over ground-truth object tracks.

A single-frame encoder represents appearance, not motion. "Crossing"
is a trajectory: a pedestrian standing at the kerb and one mid-crossing look
almost identical in any one frame. No amount of embedding quality fixes that,
because it is a representational limit rather than a quality one.

These rules are what make the project's headline query answerable. They run over
the corpus's ground-truth tracks, not over embeddings, so they need nothing from
the ingestion pipeline and can be built and tested before anything is indexed.

Because the input tracks are ground truth, the precision and recall reported for
these rules describe *the rules*, with no detector error mixed in. That
separation is the whole reason the project refuses to run an object detector.

Geometry is image-plane only: no camera calibration, no intrinsics, no
homography. Everything is expressed as a fraction of frame width and height so a
rule tuned on one resolution behaves the same on another.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# --- ego path ---------------------------------------------------------------
# A trapezoid in the lower-centre of the frame, standing in for the lane ahead.
# Wide at the bottom (near the vehicle), narrow at the top (further away).
EGO_TOP_Y = 0.55  # horizon-ish; above this the lane is too far to matter
EGO_BOTTOM_Y = 1.0
EGO_TOP_HALF_WIDTH = 0.10
EGO_BOTTOM_HALF_WIDTH = 0.35
EGO_CENTRE_X = 0.5

# A track must move at least this fraction of frame width across its dwell for
# the motion to count as crossing rather than as jitter or a parallax wobble.
MIN_HORIZONTAL_DISPLACEMENT = 0.15

# Fewer observations than this is not a trajectory, it is a coincidence.
MIN_TRACK_POINTS = 3

PEDESTRIAN_CLASSES = frozenset({"pedestrian", "person"})
CYCLIST_CLASSES = frozenset({"rider", "bicycle", "bike", "cyclist", "motorcycle", "motor"})
VEHICLE_CLASSES = frozenset({"car", "truck", "bus", "trailer", "train"})


@dataclass(frozen=True)
class TrackPoint:
    """One observation of one tracked object, in normalised image coordinates.

    Coordinates are fractions of frame width/height so rules are resolution
    independent. Converting pixel boxes happens at the reader, once.
    """

    frame_index: int
    ts_s: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def centre_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def foot_y(self) -> float:
        # The bottom edge, not the centre: where an object *is* on the road plane
        # is its contact point. Using the centre would place a tall pedestrian
        # further down the lane than they actually stand.
        return self.y2


@dataclass(frozen=True)
class Track:
    """One object's observations through a video, in frame order."""

    track_id: str
    class_name: str
    points: Sequence[TrackPoint]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError(f"track {self.track_id!r} has no points")
        indices = [p.frame_index for p in self.points]
        if indices != sorted(indices):
            raise ValueError(f"track {self.track_id!r} points are not in frame order")


@dataclass
class BehaviorEvent:
    """A detected behaviour, with the evidence that produced it."""

    kind: str
    track_id: str
    ts_start_s: float
    ts_end_s: float
    confidence: float
    evidence: dict[str, float | int | str] = field(default_factory=dict)


def ego_half_width_at(y: float) -> float:
    """Half-width of the ego trapezoid at a given height.

    Linear taper between the top and bottom widths. Above the top edge the lane
    is treated as absent rather than infinitely narrow, so callers get 0.0 and a
    containment test fails cleanly.
    """

    if y < EGO_TOP_Y or y > EGO_BOTTOM_Y:
        return 0.0
    span = EGO_BOTTOM_Y - EGO_TOP_Y
    t = (y - EGO_TOP_Y) / span if span else 0.0
    return EGO_TOP_HALF_WIDTH + t * (EGO_BOTTOM_HALF_WIDTH - EGO_TOP_HALF_WIDTH)


def in_ego_path(point: TrackPoint) -> bool:
    """Is this observation inside the lane ahead?"""

    half_width = ego_half_width_at(point.foot_y)
    if half_width <= 0.0:
        return False
    return abs(point.centre_x - EGO_CENTRE_X) <= half_width


def _crosses_centreline(points: Sequence[TrackPoint]) -> bool:
    """Did the track pass from one side of the lane centre to the other?

    Sign change on ``centre_x - 0.5``. An object that approaches the centre and
    retreats has not crossed; one that passes through has.
    """

    sides = [1 if p.centre_x >= EGO_CENTRE_X else -1 for p in points]
    return min(sides) != max(sides)


def _confidence(track: Track, inside: Sequence[TrackPoint], displacement: float) -> float:
    """Confidence from track stability, not from any model.

    Three things make an event more trustworthy: more observations, more of them
    inside the lane, and displacement well past the threshold. Capped at 0.95 —
    a deterministic rule over ground truth is still a rule, and reporting 1.0
    would claim certainty the geometry does not have.
    """

    length_factor = min(len(track.points) / 10.0, 1.0)
    inside_factor = min(len(inside) / 4.0, 1.0)
    motion_factor = min(displacement / (MIN_HORIZONTAL_DISPLACEMENT * 2), 1.0)
    raw = 0.4 * length_factor + 0.3 * inside_factor + 0.3 * motion_factor
    return round(min(raw, 0.95), 3)


def _crossing_event(track: Track, kind: str) -> BehaviorEvent | None:
    """Shared crossing test for pedestrians and cyclists.

    Fires when the track (a) is observed inside the ego path, (b) moves more than
    the displacement threshold horizontally across its dwell, and (c) crosses the
    lane centreline. All three are required: (a) alone catches someone standing
    on the kerb edge, (b) alone catches a vehicle overtaking in the next lane,
    and (c) alone catches a track that merely straddles the centre.
    """

    if len(track.points) < MIN_TRACK_POINTS:
        return None

    inside = [p for p in track.points if in_ego_path(p)]
    if not inside:
        return None

    xs = [p.centre_x for p in track.points]
    displacement = max(xs) - min(xs)
    if displacement <= MIN_HORIZONTAL_DISPLACEMENT:
        return None

    if not _crosses_centreline(track.points):
        return None

    return BehaviorEvent(
        kind=kind,
        track_id=track.track_id,
        ts_start_s=inside[0].ts_s,
        ts_end_s=inside[-1].ts_s,
        confidence=_confidence(track, inside, displacement),
        evidence={
            "points": len(track.points),
            "points_in_ego_path": len(inside),
            "horizontal_displacement": round(displacement, 4),
            "class": track.class_name,
            "first_frame": inside[0].frame_index,
            "last_frame": inside[-1].frame_index,
        },
    )


def detect_pedestrian_crossing(track: Track) -> BehaviorEvent | None:
    if track.class_name.lower() not in PEDESTRIAN_CLASSES:
        return None
    return _crossing_event(track, "pedestrian_crossing_ego_path")


def detect_cyclist_crossing(track: Track) -> BehaviorEvent | None:
    if track.class_name.lower() not in CYCLIST_CLASSES:
        return None
    return _crossing_event(track, "cyclist_crossing")


def detect_pedestrian_at_curb(track: Track) -> BehaviorEvent | None:
    """A pedestrian beside the lane who never enters it.

    Useful as a *negative* for the crossing rule during evaluation: if a corpus
    produces many of these and few crossings, the crossing threshold is probably
    too strict.
    """

    if track.class_name.lower() not in PEDESTRIAN_CLASSES:
        return None
    if len(track.points) < MIN_TRACK_POINTS:
        return None
    if any(in_ego_path(p) for p in track.points):
        return None

    near = [p for p in track.points if abs(p.centre_x - EGO_CENTRE_X) <= 0.45]
    if not near:
        return None

    return BehaviorEvent(
        kind="pedestrian_at_curb",
        track_id=track.track_id,
        ts_start_s=near[0].ts_s,
        ts_end_s=near[-1].ts_s,
        confidence=round(min(0.3 + 0.05 * len(near), 0.8), 3),
        evidence={"points": len(track.points), "points_near_lane": len(near)},
    )


def detect_vehicle_cut_in(track: Track) -> BehaviorEvent | None:
    """A vehicle that enters the lane ahead having started outside it."""

    if track.class_name.lower() not in VEHICLE_CLASSES:
        return None
    if len(track.points) < MIN_TRACK_POINTS:
        return None

    flags = [in_ego_path(p) for p in track.points]
    if flags[0] or not any(flags):
        # Already in the lane at first sight is a lead vehicle, not a cut-in.
        return None

    entry = flags.index(True)
    lateral = abs(track.points[entry].centre_x - track.points[0].centre_x)
    if lateral <= MIN_HORIZONTAL_DISPLACEMENT / 2:
        return None

    inside = [p for p, f in zip(track.points, flags, strict=True) if f]
    return BehaviorEvent(
        kind="vehicle_cut_in",
        track_id=track.track_id,
        ts_start_s=track.points[entry].ts_s,
        ts_end_s=inside[-1].ts_s,
        confidence=_confidence(track, inside, lateral),
        evidence={
            "class": track.class_name,
            "lateral_movement": round(lateral, 4),
            "entry_frame": track.points[entry].frame_index,
        },
    )


RULES = (
    detect_pedestrian_crossing,
    detect_cyclist_crossing,
    detect_vehicle_cut_in,
    detect_pedestrian_at_curb,
)


def detect_behaviors(tracks: Iterable[Track]) -> list[BehaviorEvent]:
    """Run every rule over every track.

    A track may produce at most one event per rule, and the rules are mutually
    exclusive by class, so in practice a track yields zero or one event. Results
    are sorted by start time then track id so that two runs over the same input
    produce byte-identical output — the evaluation compares runs, and a
    non-deterministic ordering would show as spurious drift.
    """

    events: list[BehaviorEvent] = []
    for track in tracks:
        for rule in RULES:
            event = rule(track)
            if event is not None:
                events.append(event)
    events.sort(key=lambda e: (e.ts_start_s, e.track_id, e.kind))
    return events


def behavior_kinds(events: Iterable[BehaviorEvent], *, min_confidence: float = 0.0) -> list[str]:
    """Distinct event kinds, for the Qdrant payload's ``behaviors`` array.

    Sorted and de-duplicated so the payload is stable across re-indexing, which
    is what makes payload comparison in tests meaningful.
    """

    return sorted({e.kind for e in events if e.confidence >= min_confidence})


__all__ = [
    "MIN_HORIZONTAL_DISPLACEMENT",
    "MIN_TRACK_POINTS",
    "BehaviorEvent",
    "RULES",
    "Track",
    "TrackPoint",
    "behavior_kinds",
    "detect_behaviors",
    "detect_cyclist_crossing",
    "detect_pedestrian_at_curb",
    "detect_pedestrian_crossing",
    "detect_vehicle_cut_in",
    "ego_half_width_at",
    "in_ego_path",
]
