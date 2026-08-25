"""Read the corpus's MOT label CSV into per-frame object counts.

This file is the whole reason the evaluation means anything. The captions in the
index were written by a vision-language model; the search reads those captions;
so scoring the search against the captions measures the model agreeing with
itself and produces a high number that says nothing (SRS FR-EVAL-06). The MOT
table is the one description of this footage that was produced independently of
the captions, which makes it the only defensible ground truth we have.

Two practical problems it has to survive.

**Size.** The table is roughly two million rows. It is read once, streamed, and
reduced to a count per class per frame — everything else is dropped, so the
resident structure is small enough to hold while the whole suite runs.

**The join.** Label rows are named ``01c71072-718028b8-0000001.jpg``: a video
identifier followed by a frame number. The index keys on ``video_id`` and
``frame_no``. If those two identifier spaces do not line up — different id
formatting, different frame origin, a different sampling rate — every lookup
misses, every query scores zero, and the report reads as catastrophically bad
retrieval rather than a broken join. :meth:`ObjectTruth.coverage` exists so that
failure is loud. Nothing here silently returns "no objects" for a frame it could
not find; the caller is told the difference between *absent* and *unmatched*.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

# Label filenames look like "<video-id>-<frame>.jpg". The video id itself contains
# hyphens, so the split has to come from the right.
_FRAME_NAME = re.compile(r"^(?P<video>.+)-(?P<frame>\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)

# Column names seen across exports of this table. Detection is by candidate list
# rather than a fixed schema because the file is produced by someone else's tool
# and a rename should cost a clear error, not a silent column of None.
_NAME_COLUMNS = ("name", "filename", "file_name", "image", "image_name", "frame_name")
_CLASS_COLUMNS = ("class", "category", "label", "class_name", "type", "object_class")
_VIDEO_COLUMNS = ("video", "video_id", "videoname", "video_name", "sequence", "seq")
_FRAME_COLUMNS = ("frame", "frame_id", "frame_no", "frame_index", "frame_idx", "frameno")

# Class names in the table, mapped onto the vocabulary the query suite speaks.
# Anything unmapped is kept under its own lowercased name rather than dropped, so
# a query can still ask for it and a coverage report can still show it.
_CLASS_ALIASES = {
    "pedestrian": "person",
    "person": "person",
    "people": "person",
    "rider": "rider",
    "car": "car",
    "truck": "truck",
    "bus": "bus",
    "train": "train",
    "motorcycle": "motorcycle",
    "motor": "motorcycle",
    "bicycle": "bicycle",
    "bike": "bicycle",
    "traffic light": "traffic_light",
    "traffic_light": "traffic_light",
    "traffic sign": "traffic_sign",
    "traffic_sign": "traffic_sign",
}


class MotFormatError(RuntimeError):
    """The CSV is not shaped the way this reader needs."""


@dataclass(frozen=True)
class FrameKey:
    video_id: str
    frame_no: int


@dataclass
class ObjectTruth:
    """Object counts per frame, plus enough bookkeeping to distrust it.

    ``counts`` maps a frame to ``{class_name: count}``. A frame present with an
    empty mapping genuinely contained no labelled objects; a frame *absent* was
    never in the table at all, and those two must not be confused — the first is
    evidence, the second is a gap.
    """

    counts: dict[FrameKey, dict[str, int]] = field(default_factory=dict)
    rows_read: int = 0
    rows_skipped: int = 0
    # Populated by lookups so a caller can ask, after the fact, how much of what
    # it asked about was actually in the table.
    _hits: int = 0
    _misses: int = 0
    _missed_videos: set[str] = field(default_factory=set)

    # -- reading ---------------------------------------------------------

    @property
    def videos(self) -> set[str]:
        return {key.video_id for key in self.counts}

    def frames_of(self, video_id: str) -> list[int]:
        return sorted(key.frame_no for key in self.counts if key.video_id == video_id)

    # -- lookup ----------------------------------------------------------

    def at(self, video_id: str, frame_no: int, *, tolerance: int = 0) -> dict[str, int] | None:
        """Counts for one frame, or ``None`` when the table does not cover it.

        ``tolerance`` allows the nearest labelled frame within N frames to answer,
        because the index samples keyframes on its own schedule and need not land
        exactly on a labelled frame. It is deliberately not unbounded: matching a
        keyframe to a label four seconds away would score the wrong moment.
        """

        exact = self.counts.get(FrameKey(video_id, frame_no))
        if exact is not None:
            self._hits += 1
            return exact

        if tolerance > 0:
            best: tuple[int, dict[str, int]] | None = None
            for offset in range(1, tolerance + 1):
                for candidate in (frame_no - offset, frame_no + offset):
                    found = self.counts.get(FrameKey(video_id, candidate))
                    if found is not None and (best is None or offset < best[0]):
                        best = (offset, found)
                if best is not None:
                    break
            if best is not None:
                self._hits += 1
                return best[1]

        self._misses += 1
        self._missed_videos.add(video_id)
        return None

    def coverage(self) -> Coverage:
        return Coverage(
            hits=self._hits,
            misses=self._misses,
            missed_videos=frozenset(self._missed_videos),
        )

    def reset_coverage(self) -> None:
        self._hits = 0
        self._misses = 0
        self._missed_videos = set()


@dataclass(frozen=True)
class Coverage:
    """How much of what was asked about the table could actually answer."""

    hits: int
    misses: int
    missed_videos: frozenset[str]

    @property
    def rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    @property
    def is_usable(self) -> bool:
        """Below this the numbers describe a broken join, not retrieval quality.

        Two thirds is not a statistical threshold; it is the point past which a
        report would mislead a reader more than it informs them.
        """

        return self.rate >= 0.66


def _detect(header: Iterable[str], candidates: tuple[str, ...]) -> str | None:
    normalised = {name.strip().lower().replace(" ", "_"): name for name in header}
    for candidate in candidates:
        if candidate in normalised:
            return normalised[candidate]
    return None


def parse_frame_name(name: str) -> FrameKey | None:
    """Split ``01c71072-718028b8-0000001.jpg`` into its video id and frame number."""

    match = _FRAME_NAME.match(name.strip())
    if match is None:
        return None
    return FrameKey(match.group("video"), int(match.group("frame")))


def normalise_class(raw: str) -> str:
    key = raw.strip().lower()
    return _CLASS_ALIASES.get(key, key.replace(" ", "_"))


def read_mot_csv(
    path: str | Path,
    *,
    limit: int | None = None,
    video_ids: Iterable[str] | None = None,
) -> ObjectTruth:
    """Stream the label CSV into per-frame counts.

    ``video_ids`` restricts the read to videos that are actually in the index,
    which matters: the table describes the full public dataset and the index holds
    a subset, so without it most of the memory would be spent on frames no query
    can ever return.
    """

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"MOT label CSV not found: {path}")

    wanted = set(video_ids) if video_ids is not None else None
    truth = ObjectTruth()
    accumulator: dict[FrameKey, dict[str, int]] = defaultdict(dict)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise MotFormatError(f"{path} has no header row")

        name_column = _detect(reader.fieldnames, _NAME_COLUMNS)
        video_column = _detect(reader.fieldnames, _VIDEO_COLUMNS)
        frame_column = _detect(reader.fieldnames, _FRAME_COLUMNS)
        class_column = _detect(reader.fieldnames, _CLASS_COLUMNS)

        if class_column is None:
            raise MotFormatError(
                f"no object-class column in {path}.\n"
                f"  header: {', '.join(reader.fieldnames)}\n"
                f"  looked for: {', '.join(_CLASS_COLUMNS)}\n"
                "Add the real name to _CLASS_COLUMNS rather than guessing downstream."
            )
        if name_column is None and not (video_column and frame_column):
            raise MotFormatError(
                f"cannot identify the frame in {path}.\n"
                f"  header: {', '.join(reader.fieldnames)}\n"
                f"  needs either a filename column ({', '.join(_NAME_COLUMNS)}) "
                f"or both a video ({', '.join(_VIDEO_COLUMNS)}) and a frame "
                f"({', '.join(_FRAME_COLUMNS)}) column."
            )

        for row in _limited(reader, limit):
            truth.rows_read += 1
            key = _key_of(row, name_column, video_column, frame_column)
            if key is None:
                truth.rows_skipped += 1
                continue
            if wanted is not None and key.video_id not in wanted:
                continue
            class_name = normalise_class(row.get(class_column) or "")
            if not class_name:
                truth.rows_skipped += 1
                continue
            bucket = accumulator[key]
            bucket[class_name] = bucket.get(class_name, 0) + 1

    truth.counts = dict(accumulator)
    return truth


_TRACK_COLUMNS = ("track_id", "id", "object_id", "trackid", "instance_id")
_BOX_COLUMNS = {
    "x1": ("x1", "xmin", "bbox_x1", "left"),
    "y1": ("y1", "ymin", "bbox_y1", "top"),
    "x2": ("x2", "xmax", "bbox_x2", "right"),
    "y2": ("y2", "ymax", "bbox_y2", "bottom"),
}
_WH_COLUMNS = {
    "x": ("x", "bbox_x", "bb_left"),
    "y": ("y", "bbox_y", "bb_top"),
    "w": ("w", "width", "bbox_w", "bb_width"),
    "h": ("h", "height", "bbox_h", "bb_height"),
}

# Frame size, needed because the behaviour rules work in normalised image
# coordinates and the label table is in pixels. BDD100K sequences are 1280x720.
DEFAULT_FRAME_WIDTH = 1280
DEFAULT_FRAME_HEIGHT = 720


class TracksUnavailable(RuntimeError):
    """The CSV has no usable bounding boxes, so trajectories cannot be rebuilt."""


def read_mot_tracks(
    path: str | Path,
    *,
    video_ids: Iterable[str] | None = None,
    limit: int | None = None,
    fps: float = 5.0,
    frame_width: int = DEFAULT_FRAME_WIDTH,
    frame_height: int = DEFAULT_FRAME_HEIGHT,
) -> dict[str, list[object]]:
    """Rebuild per-video object trajectories for the behaviour band.

    Returns ``{video_id: [eval.behavior.Track, ...]}``.

    The behaviour rules take normalised coordinates, so pixel boxes are divided
    through by the frame size here rather than inside the rules — the rules are
    also used by the ingestion pipeline, and giving them two coordinate
    conventions is how one of the two silently starts producing nonsense.

    Raises :class:`TracksUnavailable` when the table has no box columns. That is a
    legitimate outcome — the band is then reported UNAVAILABLE rather than scored
    against something invented.
    """

    from eval.behavior import Track, TrackPoint

    path = Path(path)
    wanted = set(video_ids) if video_ids is not None else None
    # video -> track key -> list of (frame_no, class, box)
    raw: dict[str, dict[str, list[tuple[int, str, tuple[float, float, float, float]]]]] = (
        defaultdict(lambda: defaultdict(list))
    )

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise MotFormatError(f"{path} has no header row")

        name_column = _detect(reader.fieldnames, _NAME_COLUMNS)
        video_column = _detect(reader.fieldnames, _VIDEO_COLUMNS)
        frame_column = _detect(reader.fieldnames, _FRAME_COLUMNS)
        class_column = _detect(reader.fieldnames, _CLASS_COLUMNS)
        track_column = _detect(reader.fieldnames, _TRACK_COLUMNS)

        corners = {part: _detect(reader.fieldnames, names) for part, names in _BOX_COLUMNS.items()}
        wh = {part: _detect(reader.fieldnames, names) for part, names in _WH_COLUMNS.items()}
        use_corners = all(corners.values())
        use_wh = all(wh.values())
        if not (use_corners or use_wh):
            raise TracksUnavailable(
                f"{path} has no bounding-box columns.\n"
                f"  header: {', '.join(reader.fieldnames)}\n"
                "  needs either x1/y1/x2/y2 or x/y/w/h.\n"
                "The behavioural band cannot be scored without trajectories."
            )
        if class_column is None:
            raise MotFormatError("no object-class column; cannot type a track")

        for row in _limited(reader, limit):
            key = _key_of(row, name_column, video_column, frame_column)
            if key is None:
                continue
            if wanted is not None and key.video_id not in wanted:
                continue
            box = _box_of(row, corners if use_corners else None, wh if use_wh else None)
            if box is None:
                continue
            class_name = normalise_class(row.get(class_column) or "")
            # Without a track id, one object per class per frame is the best that
            # can be reconstructed. Stated rather than silently assumed: it merges
            # two pedestrians into one wandering track, which suppresses crossings
            # rather than inventing them, so the resulting score is a floor.
            track_key = (row.get(track_column) or "").strip() if track_column else ""
            raw[key.video_id][f"{class_name}:{track_key or 'untracked'}"].append(
                (key.frame_no, class_name, box)
            )

    tracks: dict[str, list[object]] = {}
    for video_id, per_track in raw.items():
        built: list[object] = []
        for track_key, entries in per_track.items():
            entries.sort(key=lambda entry: entry[0])
            class_name = entries[0][1]
            points = [
                TrackPoint(
                    frame_index=frame_no,
                    ts_s=frame_no / fps,
                    x1=box[0] / frame_width,
                    y1=box[1] / frame_height,
                    x2=box[2] / frame_width,
                    y2=box[3] / frame_height,
                )
                for frame_no, _, box in entries
            ]
            if len(points) < 2:
                continue
            built.append(Track(track_id=track_key, class_name=class_name, points=points))
        if built:
            tracks[video_id] = built
    return tracks


def _box_of(
    row: dict[str, str],
    corners: dict[str, str | None] | None,
    wh: dict[str, str | None] | None,
) -> tuple[float, float, float, float] | None:
    try:
        if corners is not None:
            return (
                float(row[corners["x1"]]),  # type: ignore[index]
                float(row[corners["y1"]]),  # type: ignore[index]
                float(row[corners["x2"]]),  # type: ignore[index]
                float(row[corners["y2"]]),  # type: ignore[index]
            )
        if wh is not None:
            x = float(row[wh["x"]])  # type: ignore[index]
            y = float(row[wh["y"]])  # type: ignore[index]
            return (x, y, x + float(row[wh["w"]]), y + float(row[wh["h"]]))  # type: ignore[index]
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _limited(rows: Iterator[dict[str, str]], limit: int | None) -> Iterator[dict[str, str]]:
    if limit is None:
        yield from rows
        return
    for index, row in enumerate(rows):
        if index >= limit:
            return
        yield row


def _key_of(
    row: dict[str, str],
    name_column: str | None,
    video_column: str | None,
    frame_column: str | None,
) -> FrameKey | None:
    if name_column is not None:
        raw = row.get(name_column) or ""
        key = parse_frame_name(raw)
        if key is not None:
            return key
    if video_column is not None and frame_column is not None:
        video = (row.get(video_column) or "").strip()
        frame = (row.get(frame_column) or "").strip()
        if video and frame.isdigit():
            return FrameKey(video, int(frame))
    return None


__all__ = [
    "DEFAULT_FRAME_HEIGHT",
    "DEFAULT_FRAME_WIDTH",
    "Coverage",
    "FrameKey",
    "MotFormatError",
    "ObjectTruth",
    "TracksUnavailable",
    "normalise_class",
    "parse_frame_name",
    "read_mot_csv",
    "read_mot_tracks",
]
