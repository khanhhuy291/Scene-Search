"""In-process snapshot of every indexed keyframe's payload.

This exists to make one promise keepable: when an engineer asks for "a snowy
day" because they intend to *train* on it, they need every snowy video in the
corpus, not the twelve nearest neighbours. Completeness cannot come from an
approximate nearest-neighbour search -- that is what "approximate" means -- so it
comes from evaluating the query against every caption.

Doing that per request against Qdrant would mean paging the whole collection on
every keystroke, so the payloads are read once and held. Three facts make this a
reasonable trade rather than a lazy one:

* The collection is small and bounded: ~22k keyframes over ~880 videos, roughly
  20 MB of caption text.
* The snapshot is normally stable between writes. Ingestion and the admin caption
  refresh task increment a shared Redis generation so a changed caption causes a
  reload on the next search; the TTL remains a fallback for other writers.
* The alternative needs a full-text payload index on the collection, and the
  collection is owned by another workstream. Adding indexes to someone else's
  live index to satisfy a read path is not a change to make unilaterally.

The negation-aware matching in :mod:`search.query` also cannot be expressed as a
Qdrant text filter at all -- ``MatchText`` is substring matching with no notion of
"no visible pedestrians" meaning the opposite of "pedestrians" -- so the scan is
required regardless of how the candidates are narrowed.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from loguru import logger

from core.config import get_settings
from search.query import Clause, Polarity, concept_pattern, resolve_concept, split_clauses

# Per-concept, per-keyframe polarity plus how often the caption named it.
# Shared with the engine so a ``Polarity`` array is not passed as ``str``.
ConceptArrays: TypeAlias = dict[str, tuple[tuple[Polarity, ...], tuple[int, ...]]]

# Long enough that a burst of searches shares one snapshot, short enough that a
# re-index becomes visible without restarting the API.
DEFAULT_TTL_SECONDS = 900.0
_THREAD_OFFLOAD_MIN_FRAMES = 1000

# Qdrant page size for the initial read. Larger pages mean fewer round trips; far
# larger ones start to matter for peak memory during deserialization.
_SCROLL_PAGE = 1000
_CATALOG_GENERATION_KEY = "scenesearch:search-catalog-generation"

# Live Viettech frames are named ``frame_00034.jpg`` (or MOT-style
# ``<video-id>-0000001.jpg``) and often omit ``timestamp_sec``. The trailing
# integer is the frame index at the corpus sample rate.
_FRAME_FILE = re.compile(r"frame[_-]?(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)
_MOT_FRAME_FILE = re.compile(r"-(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _frame_no_from_name(value: Any) -> int | None:
    if not value:
        return None
    name = str(value).rsplit("/", 1)[-1]
    match = _FRAME_FILE.search(name) or _MOT_FRAME_FILE.search(name)
    return int(match.group(1)) if match else None


def _infer_frame_no(payload: dict[str, Any]) -> int:
    for key in ("frame_no", "frame_idx", "frame_index", "frame_id"):
        parsed = _int_or_none(payload.get(key))
        if parsed is not None:
            return parsed
    for key in ("frame_name", "minio_path", "minio_thumbnail_key", "frame_minio_key"):
        parsed = _frame_no_from_name(payload.get(key))
        if parsed is not None:
            return parsed
    return -1


def _infer_timestamp_s(payload: dict[str, Any], frame_no: int) -> float:
    for key in ("video_second", "timestamp_sec", "ts_start_s", "timestamp_s"):
        raw = payload.get(key)
        if raw is None or raw == "":
            continue
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            continue
    if frame_no >= 0:
        fps = get_settings().search.keyframe_fps
        return max(0.0, frame_no / fps)
    return 0.0


@dataclass(frozen=True, slots=True)
class Keyframe:
    """One indexed keyframe, as the search path needs it.

    ``slots`` because there are ~22k of these resident and the attribute
    dictionaries would otherwise be the largest single cost of the snapshot.
    """

    point_id: str
    video_id: str
    timestamp_s: float
    frame_no: int
    caption: str
    thumbnail_key: str | None
    video_key: str | None
    # Structured payload fields
    people: tuple[str, ...] | None = None
    vehicles: tuple[str, ...] | None = None
    traffic_elements: tuple[str, ...] = ()
    weather: str | None = None
    time_of_day: str | None = None
    road_condition: str | None = None
    scene_type: str | None = None
    retrieval_tags: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None
    ocr: str = ""
    end_timestamp_s: float | None = None
    dataset: str | None = None
    granularity: str = "frame"
    objects: tuple[str, ...] = ()
    object_counts: dict[str, int] | None = None
    behaviors: tuple[str, ...] = ()

    @property
    def has_thumbnail(self) -> bool:
        return bool(self.thumbnail_key)

    @property
    def renderable(self) -> bool:
        """Both an image to show and a clip to open."""
        return bool(self.thumbnail_key) and bool(self.video_key)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _environment(payload: dict[str, Any]) -> dict[str, str]:
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    meta_scene = meta.get("scene") if isinstance(meta.get("scene"), dict) else {}
    raw_env = payload.get("environment") if isinstance(payload.get("environment"), dict) else {}

    weather = meta_scene.get("weather") or raw_env.get("weather") or payload.get("weather")
    time_of_day = (
        meta_scene.get("time_of_day")
        or raw_env.get("time_of_day")
        or payload.get("timeofday")
        or payload.get("time_of_day")
    )
    road = (
        meta_scene.get("road_surface")
        or meta_scene.get("road_type")
        or raw_env.get("road_condition")
        or payload.get("road_condition")
    )
    scene_type = (
        meta_scene.get("scene_type")
        or meta_scene.get("road_type")
        or raw_env.get("scene_type")
        or payload.get("scene_type")
        or payload.get("scene")
    )
    return {
        "weather": str(weather).strip() if weather and weather != "unknown" else "",
        "time_of_day": str(time_of_day).strip() if time_of_day and time_of_day != "unknown" else "",
        "road_condition": str(road).strip() if road and road != "unknown" else "",
        "scene_type": str(scene_type).strip() if scene_type and scene_type != "unknown" else "",
    }


def keyframe_from_payload(point_id: str, payload: dict[str, Any]) -> Keyframe | None:
    """Adapt one Qdrant payload, or None when it is not a usable keyframe."""

    video_id = payload.get("video_id")
    if not video_id:
        return None

    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    caption = payload.get("caption") or meta.get("caption") or payload.get("qwen_caption") or ""

    frame_no = _infer_frame_no(payload)
    timestamp_s = _infer_timestamp_s(payload, frame_no)

    env = _environment(payload)
    ocr = payload.get("ocr") or meta.get("ocr")
    retrieval_tags = _string_tuple(meta.get("retrieval_tags") or payload.get("retrieval_tags"))

    thumbnail_key = (
        payload.get("minio_path")
        or payload.get("minio_thumbnail_key")
        or payload.get("minio_keyframe_key")
        or payload.get("frame_minio_key")
        or payload.get("thumbnail_key")
        or payload.get("thumbnail_url")
        or payload.get("image_path")
        or payload.get("frame_name")
    )
    video_key = (
        payload.get("minio_video_key") or payload.get("video_key") or payload.get("video_path")
    )
    if not video_key and video_id and payload.get("minio_path"):
        video_key = f"videos/{video_id}.mov"

    # Traffic elements extraction
    traffic = meta.get("traffic") if isinstance(meta.get("traffic"), dict) else {}
    vehicles_list: list[str] = []
    people_list: list[str] = []
    for k, v in traffic.items():
        if v and v != "none" and v != "0":
            if k in ("pedestrians", "people", "person"):
                people_list.append(f"{k}: {v}")
            else:
                vehicles_list.append(f"{k}: {v}")

    vehicles_tuple = (
        tuple(vehicles_list)
        if vehicles_list
        else (_string_tuple(payload["vehicles"]) if "vehicles" in payload else None)
    )
    people_tuple = (
        tuple(people_list)
        if people_list
        else (_string_tuple(payload["people"]) if "people" in payload else None)
    )

    return Keyframe(
        point_id=point_id,
        video_id=str(video_id),
        timestamp_s=max(0.0, timestamp_s),
        frame_no=frame_no,
        caption=str(caption),
        thumbnail_key=str(thumbnail_key) if thumbnail_key else None,
        video_key=str(video_key) if video_key else None,
        people=people_tuple,
        vehicles=vehicles_tuple,
        traffic_elements=_string_tuple(payload.get("traffic_elements")),
        weather=env["weather"] or None,
        time_of_day=env["time_of_day"] or None,
        road_condition=env["road_condition"] or None,
        scene_type=env["scene_type"] or None,
        retrieval_tags=retrieval_tags,
        metadata=meta if meta else None,
        ocr=str(ocr).strip() if ocr else "",
        end_timestamp_s=(
            max(timestamp_s, float(payload["ts_end_s"]))
            if payload.get("ts_end_s") is not None
            else None
        ),
        dataset=str(payload["dataset"]) if payload.get("dataset") else None,
        granularity=str(payload.get("granularity") or "frame"),
        objects=_string_tuple(payload.get("objects")),
        object_counts=(
            {str(key): int(value) for key, value in payload["object_counts"].items()}
            if isinstance(payload.get("object_counts"), dict)
            else None
        ),
        behaviors=_string_tuple(payload.get("behaviors")),
    )


_WEATHER_TO_CONCEPT = {
    "sunny": "clear_sky",
    "clear": "clear_sky",
    "sunshine": "clear_sky",
    "rain": "rain",
    "rainy": "rain",
    "raining": "rain",
    "drizzle": "rain",
    "snow": "snow",
    "snowy": "snow",
    "fog": "fog",
    "foggy": "fog",
    "overcast": "overcast",
    "cloudy": "overcast",
}
_WEATHER_CONCEPTS = frozenset(_WEATHER_TO_CONCEPT.values())
_TIME_TO_CONCEPT = {
    "daytime": "day",
    "day": "day",
    "night": "night",
    "night-time": "night",
    "nighttime": "night",
    "dusk": "dusk",
    "evening": "dusk",
    "dawn": "dawn",
    "sunrise": "dawn",
}
_TIME_CONCEPTS = frozenset(_TIME_TO_CONCEPT.values())
_VEHICLE_CONCEPTS = frozenset({"car", "truck", "bus", "motorcycle", "cyclist"})


def _norm(value: str) -> str:
    return value.strip().lower().replace("_", " ").replace("-", " ")


def structured_polarity(frame: Keyframe, concept: str) -> Polarity:
    """Hard evidence from Huy's structured fields. ``unknown`` means "fall back".

    Structured presence/absence beats the caption: an empty ``people`` list is
    observed absence even if the caption still mentions pedestrians, and a
    ``weather: sunny`` value is not rain no matter how the prose is phrased.
    """

    if frame.weather:
        mapped = _WEATHER_TO_CONCEPT.get(_norm(frame.weather).replace(" ", ""))
        if mapped is None:
            mapped = _WEATHER_TO_CONCEPT.get(_norm(frame.weather))
        if mapped is not None and concept in _WEATHER_CONCEPTS:
            return "present" if concept == mapped else "absent"

    if frame.time_of_day:
        mapped = _TIME_TO_CONCEPT.get(_norm(frame.time_of_day).replace(" ", ""))
        if mapped is None:
            mapped = _TIME_TO_CONCEPT.get(_norm(frame.time_of_day))
        if mapped is not None and concept in _TIME_CONCEPTS:
            return "present" if concept == mapped else "absent"

    if frame.road_condition and concept == "wet_road":
        condition = _norm(frame.road_condition)
        if any(word in condition for word in ("wet", "slick", "damp")):
            return "present"
        if "dry" in condition:
            return "absent"

    if frame.people is not None and concept == "people":
        return "present" if frame.people else "absent"

    if frame.people is not None and concept == "cyclist":
        blob = " ".join(frame.people)
        if concept_pattern("cyclist").search(blob):
            return "present"
        if not frame.people:
            return "absent"

    if frame.vehicles is not None and concept in _VEHICLE_CONCEPTS:
        blob = " ".join(frame.vehicles)
        if concept_pattern(concept).search(blob):
            return "present"
        if not frame.vehicles:
            return "absent"

    if (
        frame.traffic_elements
        and concept == "traffic_light"
        and concept_pattern(concept).search(" ".join(frame.traffic_elements))
    ):
        return "present"

    return "unknown"


def _resolve_concepts(
    frames: tuple[Keyframe, ...],
    clauses: tuple[tuple[Clause, ...], ...],
    concepts: tuple[str, ...],
) -> ConceptArrays:
    """Resolve concepts against structured fields first, then caption clauses."""

    started = time.monotonic()
    resolved: ConceptArrays = {}
    for concept in concepts:
        polarities: list[Polarity] = []
        mentions: list[int] = []
        conflicts = 0
        for frame, caption_clauses in zip(frames, clauses, strict=True):
            caption_polarity, found = resolve_concept(caption_clauses, concept)
            structured = structured_polarity(frame, concept)
            if structured == "present":
                polarities.append("present")
                mentions.append(max(found, 1))
            elif structured == "absent" and caption_polarity == "present":
                # The two sources disagree: an extractor field asserts the concept
                # is absent while the caption positively describes it.
                #
                # An empty ``people: []`` has two possible meanings and the payload
                # does not distinguish them -- "the extractor looked and saw none",
                # or "the extractor produced nothing for this frame". Letting it
                # override the caption is right for the first reading and
                # catastrophic for the second: "pedestrians crossing the street"
                # would reject the very frames whose captions say exactly that,
                # while still reporting ``exhaustive: true``.
                #
                # The caption wins, because the two failure modes are not
                # symmetrical. Trusting the caption when the extractor was right
                # costs *precision* -- a frame reaches a human who looks at it and
                # rejects it, which is what the review gate is for. Trusting the
                # extractor when it simply produced nothing costs *recall*, on the
                # most common query in the product, invisibly.
                conflicts += 1
                polarities.append("present")
                mentions.append(max(found, 1))
            elif structured == "absent":
                polarities.append("absent")
                mentions.append(0)
            else:
                polarities.append(caption_polarity)
                mentions.append(found)
        resolved[concept] = (tuple(polarities), tuple(mentions))
        if conflicts:
            total = len(frames) or 1
            logger.warning(
                "Concept {concept!r}: {conflicts} of {total} frames ({rate:.1%}) have a "
                "structured field asserting absence while the caption asserts presence. "
                "Resolved to 'present' (caption wins). A high rate means the extractor "
                "writes an empty list for 'not extracted' rather than 'observed none'.",
                concept=concept,
                conflicts=conflicts,
                total=total,
                rate=conflicts / total,
            )
    logger.debug(
        "Resolved {count} concept(s) over {frames} captions in {elapsed:.2f}s",
        count=len(concepts),
        frames=len(clauses),
        elapsed=time.monotonic() - started,
    )
    return resolved


@dataclass(frozen=True, slots=True)
class CatalogView:
    """One request's pinned view of the snapshot.

    Everything downstream is positionally aligned to ``frames``: the clause
    tuples, and the per-frame polarity arrays derived from them. A reload
    replaces all of it at once, so a request that reads ``frames`` before an
    await and the concept arrays after one can end up indexing the new tuple
    with the old array's positions -- returning, verifiably, sunny frames for
    "snowy day" with ``confirmed: ["snow"]`` attached.

    Pinning is what makes that impossible: a request takes one view and never
    reads through the mutable catalog again. ``generation`` lets the catalog
    tell whether a view it is handed is still the current one.
    """

    generation: int
    frames: tuple[Keyframe, ...]
    index_of: Mapping[str, int]
    per_video: Mapping[str, int]
    clauses: tuple[tuple[Clause, ...], ...]
    ocr_by_value: Mapping[str, str]
    captionless: bool

    def position_of(self, point_id: str) -> int | None:
        return self.index_of.get(point_id)

    def keyframes_in_video(self, video_id: str) -> int:
        return self.per_video.get(video_id, 0)


class KeyframeCatalog:
    """A point-in-time snapshot of the collection's payloads."""

    def __init__(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._frames: tuple[Keyframe, ...] = ()
        self._by_id: dict[str, Keyframe] = {}
        self._index_of: dict[str, int] = {}
        self._per_video: dict[str, int] = {}
        self._loaded_at: float | None = None
        self._lock = asyncio.Lock()
        self._shared_generation: int | None = None
        # Bumped on every load. Anything derived from a snapshot carries the
        # generation it was derived under, so misalignment is detectable
        # rather than silent.
        self._generation = 0
        # Negation scopes per caption, positionally aligned to ``_frames``.
        self._clauses: tuple[tuple[Clause, ...], ...] = ()
        # Concept name -> per-frame (polarity, mention count), also aligned to
        # ``_frames``. Built on first use of each concept and kept, because a
        # caption's verdict for a concept cannot change while the snapshot lives.
        self._concepts: ConceptArrays = {}
        self._ocr_by_value: dict[str, str] = {}
        self._captionless = True

    # -- state -------------------------------------------------------------

    @property
    def loaded(self) -> bool:
        return self._loaded_at is not None

    @property
    def stale(self) -> bool:
        if self._loaded_at is None:
            return True
        return (time.monotonic() - self._loaded_at) > self._ttl

    @property
    def frames(self) -> tuple[Keyframe, ...]:
        return self._frames

    @property
    def video_count(self) -> int:
        return len(self._per_video)

    def get(self, point_id: str) -> Keyframe | None:
        return self._by_id.get(point_id)

    def position_of(self, point_id: str) -> int | None:
        """Index of a keyframe in :attr:`frames`, for the aligned concept arrays."""

        return self._index_of.get(point_id)

    def keyframes_in_video(self, video_id: str) -> int:
        return self._per_video.get(video_id, 0)

    def view(self) -> CatalogView:
        """Pin the current snapshot for the life of one request."""

        return CatalogView(
            generation=self._generation,
            frames=self._frames,
            index_of=self._index_of,
            per_video=self._per_video,
            clauses=self._clauses,
            ocr_by_value=self._ocr_by_value,
            captionless=self._captionless,
        )

    # -- concept resolution ------------------------------------------------

    async def concept_arrays(self, view: CatalogView, concepts: tuple[str, ...]) -> ConceptArrays:
        """Per-frame polarity and mention counts, aligned to ``view``.

        Resolving one concept across the corpus costs about half a second, so it
        is done once per concept per snapshot rather than once per search. The work
        is handed to a thread: it is pure CPU over ~22k captions and would
        otherwise stall the event loop, which on a single-worker deployment means
        stalling every other request.

        The thread is also where a reload can land. Resolution therefore runs
        against ``view.clauses`` -- the tuple the caller pinned -- rather than
        ``self._clauses``, and the memo is only updated if the snapshot is still
        the one the arrays describe. Without both halves, a reload during the
        await produces arrays indexed by the old positions and read against the
        new frames: not an error, just quietly wrong answers with a completeness
        claim attached.
        """

        memo = self._concepts if view.generation == self._generation else {}
        missing = tuple(concept for concept in concepts if concept not in memo)
        resolved: ConceptArrays = {}
        if missing:
            if len(view.frames) < _THREAD_OFFLOAD_MIN_FRAMES:
                resolved = _resolve_concepts(view.frames, view.clauses, missing)
            else:
                resolved = await asyncio.to_thread(
                    _resolve_concepts, view.frames, view.clauses, missing
                )
            # Only cache when the snapshot did not move underneath us. Caching a
            # stale array is worse than recomputing: it poisons every later
            # request for that concept until the next reload clears it.
            if view.generation == self._generation:
                self._concepts.update(resolved)

        out: ConceptArrays = {}
        for concept in concepts:
            arrays = resolved.get(concept) or memo.get(concept)
            if arrays is None:  # pragma: no cover - defensive
                arrays = _resolve_concepts(view.frames, view.clauses, (concept,))[concept]
            out[concept] = arrays
        return out

    def contradicting_positions(
        self,
        view: CatalogView,
        concept_arrays: ConceptArrays,
        concepts: tuple[str, ...],
    ) -> dict[str, int]:
        """Per video, how many keyframes explicitly show an excluded concept.

        The number behind "clean at 0:12 — people appear in 4 other moments of
        this clip". A user who is shown that trusts a result they would otherwise
        think was a bug; a user who is shown a video card and finds a pedestrian
        eight seconds later concludes the search is broken.

        It is a **lower bound**, and has to be labelled as one. A caption that
        never mentions people resolves to ``unknown``, not to absence
        (:func:`search.query.resolve_concept`), so this counts only the moments a
        caption positively describes. The honest phrasing is "moments whose
        description mentions people", not "moments containing people".

        One pass over the pinned frame tuple, no I/O: the polarity arrays were
        already computed for the filter.
        """

        counts: dict[str, int] = {}
        if not concepts:
            return counts
        arrays = [concept_arrays[c][0] for c in concepts if c in concept_arrays]
        if not arrays:
            return counts
        for position, keyframe in enumerate(view.frames):
            if any(array[position] == "present" for array in arrays):
                counts[keyframe.video_id] = counts.get(keyframe.video_id, 0) + 1
        return counts

    # -- loading -----------------------------------------------------------

    async def ensure_loaded(self, client: Any, *, force: bool = False) -> None:
        """Populate the snapshot if it is missing or past its TTL.

        The lock makes a cold start under concurrent requests read the
        collection once rather than once per request; the second waiter finds a
        fresh snapshot and returns.
        """

        shared_generation = await self._read_shared_generation()
        shared_changed = (
            shared_generation is not None and shared_generation != self._shared_generation
        )
        if not force and self.loaded and not self.stale and not shared_changed:
            return
        async with self._lock:
            shared_generation = await self._read_shared_generation()
            shared_changed = (
                shared_generation is not None and shared_generation != self._shared_generation
            )
            if not force and self.loaded and not self.stale and not shared_changed:
                return
            await self._load(client)
            if shared_generation is not None:
                self._shared_generation = shared_generation

    async def _read_shared_generation(self) -> int | None:
        """Read the cross-process invalidation counter; TTL remains the fallback."""

        try:
            from infrastructure.redis import get_redis_client

            value = await get_redis_client().get(_CATALOG_GENERATION_KEY)
            return int(value) if value is not None else None
        except Exception as exc:
            logger.debug("Search catalog generation check unavailable: {error}", error=exc)
            return None

    async def _load(self, client: Any) -> None:
        collection = get_settings().qdrant.collection
        started = time.monotonic()

        frames: list[Keyframe] = []
        offset: Any = None
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=_SCROLL_PAGE,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for point in points:
                keyframe = keyframe_from_payload(str(point.id), point.payload or {})
                if keyframe is not None:
                    frames.append(keyframe)
            if offset is None:
                break

        per_video: dict[str, int] = {}
        ocr_by_value: dict[str, str] = {}
        has_caption = False
        for keyframe in frames:
            per_video[keyframe.video_id] = per_video.get(keyframe.video_id, 0) + 1
            if keyframe.caption.strip():
                has_caption = True
            token = keyframe.ocr.strip()
            if token:
                ocr_by_value.setdefault(token.casefold(), token)

        # Split every caption up front, in a thread. It is the dominant cost of
        # caption matching and is shared by every concept, so paying it once here
        # is what keeps a search off the multi-second path.
        def build_clauses() -> tuple[tuple[Clause, ...], ...]:
            return tuple(split_clauses(keyframe.caption) for keyframe in frames)

        if len(frames) < _THREAD_OFFLOAD_MIN_FRAMES:
            clauses = build_clauses()
        else:
            clauses = await asyncio.to_thread(build_clauses)

        self._frames = tuple(frames)
        self._by_id = {keyframe.point_id: keyframe for keyframe in frames}
        self._index_of = {keyframe.point_id: position for position, keyframe in enumerate(frames)}
        self._per_video = per_video
        self._ocr_by_value = ocr_by_value
        self._captionless = not has_caption
        self._clauses = clauses
        # A reload invalidates the derived arrays: they are positionally aligned
        # to the frame tuple that was just replaced.
        self._concepts = {}
        self._generation += 1
        self._loaded_at = time.monotonic()

        without_thumbnail = sum(1 for keyframe in frames if not keyframe.has_thumbnail)
        logger.info(
            "Loaded keyframe catalog: {frames} keyframes across {videos} videos "
            "in {elapsed:.2f}s ({missing} without a thumbnail)",
            frames=len(frames),
            videos=len(per_video),
            elapsed=time.monotonic() - started,
            missing=without_thumbnail,
        )


_catalog: KeyframeCatalog | None = None


def get_catalog() -> KeyframeCatalog:
    """Return the process-wide catalog, without loading it."""

    global _catalog
    if _catalog is None:
        _catalog = KeyframeCatalog()
    return _catalog


def reset_catalog() -> None:
    """Drop the cached catalog (used by tests)."""

    global _catalog
    _catalog = None


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ConceptArrays",
    "Keyframe",
    "KeyframeCatalog",
    "get_catalog",
    "keyframe_from_payload",
    "reset_catalog",
    "structured_polarity",
]
