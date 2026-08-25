"""Deterministic synthetic Qdrant points for unit tests.

The live search path reads Huy's Viettech collection (``Scences``), not these
points. This module still exists so upsert/filter/id tests can run without that
index. Vectors are hashes and semantically meaningless.

**What it does and does not prove.** Every filter, every payload index, every
prefilter, every batch boundary and every id collision is exercised for real
against a real Qdrant. *Relevance is not.* The vectors are hashes; the nearest
neighbour of a query is arbitrary. Never compute a retrieval metric against a
seeded index, for the same reason precision@k is never computed on the synthetic
fixture frames.

Scope note: this writes to Qdrant only. Postgres rows are the corpus repository's
job (`app/repositories/corpus.py`, owner D) and this module deliberately does not
reach into that, so the two can land independently.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.config import get_settings
from search.index import upsert_points
from search.points import ScenePayload, build_point

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

# Fixed so two developers seeding with the same arguments get byte-identical
# points. A random seed here would make "it works on my machine" literally true.
SEED_NAMESPACE = uuid.UUID("2f8a1c3d-5b6e-4a7f-9c0d-8e1f2a3b4c5d")

WEATHER = ("clear", "rainy", "snowy", "overcast", "foggy")
TIMEOFDAY = ("daytime", "night", "dawn/dusk")
SCENE = ("city street", "highway", "residential", "parking lot", "tunnel")
OBJECT_CLASSES = ("person", "car", "truck", "bus", "bike", "traffic light", "traffic sign")
BEHAVIORS = ("pedestrian_crossing_ego_path", "cyclist_crossing", "vehicle_cut_in")


def _rng_stream(*parts: object) -> Iterator[int]:
    """Endless deterministic byte stream keyed on the given parts.

    Re-hashing a counter rather than using ``random`` keeps this independent of
    global interpreter state, so seeding inside a test cannot be perturbed by
    anything else that happens to call ``random.seed``.
    """

    material = "|".join(str(p) for p in parts).encode("utf-8")
    counter = 0
    while True:
        digest = hashlib.sha256(material + counter.to_bytes(8, "big")).digest()
        yield from digest
        counter += 1


def _pick(stream: Iterator[int], options: Sequence[str]) -> str:
    return options[next(stream) % len(options)]


def deterministic_vector(*parts: object, dimension: int | None = None) -> list[float]:
    """A unit vector derived from the given parts.

    L2-normalised because the collection uses cosine distance and every real
    vector arrives normalised; an unnormalised seed vector would behave
    differently under quantisation and quietly invalidate any latency comparison.
    """

    size = dimension or get_settings().qdrant.vector_size
    stream = _rng_stream("vector", *parts)
    # Map bytes to [-1, 1] so vectors spread over the sphere rather than
    # clustering in the positive orthant, which would make every pair similar.
    values = [(next(stream) / 127.5) - 1.0 for _ in range(size)]
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0.0:  # pragma: no cover - unreachable for sha256 output
        values[0], norm = 1.0, 1.0
    return [v / norm for v in values]


@dataclass(frozen=True)
class SeededVideo:
    """What was generated for one video, so a test can assert against it."""

    video_id: str
    frame_ids: tuple[str, ...]
    segment_ids: tuple[str, ...]
    weather: str
    timeofday: str
    scene: str
    objects: tuple[str, ...]
    behaviors: tuple[str, ...]


def _video_id(index: int) -> str:
    return str(uuid.uuid5(SEED_NAMESPACE, f"video:{index}"))


def build_seed_points(
    *,
    videos: int = 5,
    segments_per_video: int = 4,
    frames_per_segment: int = 5,
    dataset: str = "seed",
    dimension: int | None = None,
) -> tuple[list[object], list[SeededVideo]]:
    """Build points and a description of them. Pure — touches no service.

    Returns ``(points, seeded)`` so a caller can upsert the points and then
    assert against the metadata without re-deriving it.
    """

    if videos < 1 or segments_per_video < 1 or frames_per_segment < 1:
        raise ValueError("videos, segments_per_video and frames_per_segment must all be >= 1")

    settings = get_settings()
    model_version = settings.ml.model_version
    size = dimension or settings.qdrant.vector_size

    points: list[object] = []
    seeded: list[SeededVideo] = []

    for v in range(videos):
        video_id = _video_id(v)
        stream = _rng_stream("meta", video_id)
        weather = _pick(stream, WEATHER)
        timeofday = _pick(stream, TIMEOFDAY)
        scene = _pick(stream, SCENE)

        object_count = 1 + (next(stream) % 4)
        objects = tuple(sorted({_pick(stream, OBJECT_CLASSES) for _ in range(object_count)}))
        object_counts = {name: 1 + (next(stream) % 5) for name in objects}

        # Every third video carries a behaviour tag. Keyed on the video *index*
        # rather than on the hash stream deliberately: a hash gives roughly a
        # third on average but can produce zero for a small corpus, which leaves
        # behaviour filters with nothing to match and silently untested. Indexing
        # guarantees at least one match from one video and at least one
        # non-match from two.
        behaviors: tuple[str, ...] = ()
        if v % 3 == 0:
            behaviors = (_pick(stream, BEHAVIORS),)

        frame_ids: list[str] = []
        segment_ids: list[str] = []

        for s in range(segments_per_video):
            segment_id = str(uuid.uuid5(SEED_NAMESPACE, f"segment:{video_id}:{s}"))
            segment_ids.append(segment_id)
            seg_start = float(s * frames_per_segment)
            seg_end = float((s + 1) * frames_per_segment - 1)

            for f in range(frames_per_segment):
                frame_id = str(uuid.uuid5(SEED_NAMESPACE, f"frame:{video_id}:{s}:{f}"))
                frame_ids.append(frame_id)
                ts = seg_start + f
                points.append(
                    build_point(
                        "frame",
                        frame_id,
                        deterministic_vector("frame", frame_id, dimension=size),
                        ScenePayload(
                            frame_id=frame_id,
                            segment_id=None,
                            video_id=video_id,
                            dataset=dataset,
                            granularity="frame",
                            ts_start_s=ts,
                            ts_end_s=ts,
                            model_version=model_version,
                            split="val",
                            weather=weather,
                            timeofday=timeofday,
                            scene=scene,
                            objects=list(objects),
                            object_counts=object_counts,
                            behaviors=list(behaviors),
                        ),
                    )
                )

            points.append(
                build_point(
                    "segment",
                    segment_id,
                    deterministic_vector("segment", segment_id, dimension=size),
                    ScenePayload(
                        frame_id=None,
                        segment_id=segment_id,
                        video_id=video_id,
                        dataset=dataset,
                        granularity="segment",
                        ts_start_s=seg_start,
                        ts_end_s=seg_end,
                        model_version=model_version,
                        split="val",
                        weather=weather,
                        timeofday=timeofday,
                        scene=scene,
                        objects=list(objects),
                        object_counts=object_counts,
                        behaviors=list(behaviors),
                    ),
                )
            )

        seeded.append(
            SeededVideo(
                video_id=video_id,
                frame_ids=tuple(frame_ids),
                segment_ids=tuple(segment_ids),
                weather=weather,
                timeofday=timeofday,
                scene=scene,
                objects=objects,
                behaviors=behaviors,
            )
        )

    return points, seeded


async def seed_qdrant(
    *,
    videos: int = 5,
    segments_per_video: int = 4,
    frames_per_segment: int = 5,
    dataset: str = "seed",
    client: AsyncQdrantClient | None = None,
) -> tuple[int, list[SeededVideo]]:
    """Generate and upsert. Returns the number of points written and what they were.

    Idempotent: point ids are derived from the same namespace every time, so
    re-seeding overwrites rather than duplicating. That is the same property real
    ingestion relies on, which makes this a genuine exercise of it.
    """

    points, seeded = build_seed_points(
        videos=videos,
        segments_per_video=segments_per_video,
        frames_per_segment=frames_per_segment,
        dataset=dataset,
    )
    written = await upsert_points(points, client=client)
    return written, seeded


__all__ = [
    "BEHAVIORS",
    "OBJECT_CLASSES",
    "SCENE",
    "SEED_NAMESPACE",
    "SeededVideo",
    "TIMEOFDAY",
    "WEATHER",
    "build_seed_points",
    "deterministic_vector",
    "seed_qdrant",
]
