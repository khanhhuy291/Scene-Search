"""Aggregate observations without inventing temporal or co-occurrence evidence."""

from collections import Counter
from typing import Any

from core.ingestion import METADATA_PROMPT_VERSION
from pipelines.common.metadata import (
    RoadAttributes,
    SceneAttributes,
    TemporalObservation,
    TrafficControl,
    unknown_metadata,
)
from pipelines.common.types import FrameRecord, SceneRecord
from schemas.scene_evidence import SceneEvidence, SceneObservation
from search.query import (
    TIME_TO_CONCEPT,
    WEATHER_TO_CONCEPT,
    concepts_in_phrase,
    resolve_concept,
    split_clauses,
)


def canonical_concepts(values: list[str]) -> set[str]:
    return {
        concept
        for value in values
        for concept in (concepts_in_phrase(value.replace("_", " ")) or (value.strip().lower(),))
        if concept
    }


def observation_from_frame(frame: FrameRecord) -> SceneObservation:
    data = frame.metadata.get("vlm_data") or unknown_metadata(
        [], status="failed", reason="metadata_missing", timestamp_ms=frame.timestamp_ms
    )
    enrichment = data["enrichment"]
    status = enrichment["status"]
    attributes = data["metadata"]
    detector_counts = dict(Counter(d.class_name for d in frame.detections))
    counts = dict(detector_counts)
    objects = set(counts)
    positive = canonical_concepts(list(counts))
    negative: set[str] = set()
    unknown: set[str] = set()
    if status == "success":
        objects.update(data.get("objects", []))
        for name, count in data.get("object_counts", {}).items():
            if count is not None and name not in counts:
                counts[name] = count
        positive |= canonical_concepts(list(objects))
        positive |= canonical_concepts(data.get("present_concepts", []))
        negative = canonical_concepts(data.get("absent_concepts", []))
        unknown = canonical_concepts(data.get("unknown_concepts", []))
        caption = attributes["caption"]
        clauses = split_clauses(caption)
        for concept in concepts_in_phrase(caption):
            polarity, _ = resolve_concept(clauses, concept)
            if polarity == "present":
                positive.add(concept)
            elif polarity == "absent":
                negative.add(concept)
        scene = attributes.get("scene", {})
        positive |= canonical_concepts([v for v in scene.values() if v and v != "unknown"])
        for field, mapping in (("weather", WEATHER_TO_CONCEPT), ("time_of_day", TIME_TO_CONCEPT)):
            if scene.get(field) in mapping:
                positive.add(mapping[scene[field]])
        if scene.get("road_surface") == "wet":
            positive.add("wet_road")
        road = attributes.get("road", {})
        if road.get("intersection") is True or road.get("roundabout") is True:
            positive.add("intersection")
        traffic = attributes.get("traffic", {})
        positive |= canonical_concepts(
            [k for k, v in traffic.items() if v not in ("unknown", "none")]
        )
        if attributes.get("traffic_control", {}).get("traffic_light", {}).get("present") is True:
            positive.add("traffic_light")
        # Time-of-day labels describe one instant. Weather concepts are not
        # grouped here: e.g. rain and fog can legitimately coexist.
        conflicting_time = len(positive & set(TIME_TO_CONCEPT.values())) > 1
        if positive & negative or unknown & (positive | negative) or conflicting_time:
            # Contradictory provider evidence is unusable; detector observations survive.
            data = unknown_metadata(
                list(detector_counts),
                status="failed",
                reason="conflicting_evidence",
                timestamp_ms=frame.timestamp_ms,
            )
            enrichment, attributes, status = data["enrichment"], data["metadata"], "failed"
            counts = detector_counts
            objects = set(counts)
            positive, negative, unknown = canonical_concepts(list(counts)), set(), set()
    return SceneObservation(
        frame_index=frame.frame_index,
        timestamp_ms=frame.timestamp_ms,
        source=enrichment["source"],
        status=status,
        model=enrichment.get("model"),
        prompt_version=enrichment.get("prompt_version", METADATA_PROMPT_VERSION)
        if status == "success"
        else None,
        reason=enrichment.get("reason"),
        caption=attributes.get("caption", ""),
        attributes=attributes,
        present_concepts=sorted(positive),
        absent_concepts=sorted(negative),
        unknown_concepts=sorted(unknown),
        objects=sorted(objects),
        object_counts=counts,
        behaviors=sorted({b.kind for b in frame.behaviors}),
    )


def _consistent_attributes(
    values: list[dict[str, Any]], defaults: dict[str, Any]
) -> dict[str, Any]:
    result = {}
    for name, unknown in defaults.items():
        observed = [value.get(name, unknown) for value in values]
        if isinstance(unknown, dict):
            result[name] = _consistent_attributes(observed, unknown)
        else:
            result[name] = (
                observed[0] if observed and all(v == observed[0] for v in observed) else unknown
            )
    return result


def aggregate_observations(
    observations: list[SceneObservation],
    *,
    sampled_count: int | None,
    representative_frame_index: int,
    representative_timestamp_ms: int,
    sequence_caption: str | None = None,
    temporal_observations: list[TemporalObservation] | None = None,
) -> dict[str, Any]:
    observations = sorted(observations, key=lambda o: (o.timestamp_ms, o.frame_index))
    successful = [o for o in observations if o.status == "success"]
    summary = _consistent_attributes(
        [o.attributes.get("scene", {}) for o in successful], SceneAttributes().model_dump()
    )
    road = _consistent_attributes(
        [o.attributes.get("road", {}) for o in successful], RoadAttributes().model_dump()
    )
    traffic_control = _consistent_attributes(
        [o.attributes.get("traffic_control", {}) for o in successful], TrafficControl().model_dump()
    )
    traffic = _consistent_attributes(
        [o.attributes.get("traffic", {}) for o in successful],
        {key: "unknown" for o in successful for key in o.attributes.get("traffic", {})},
    )
    positives = sorted({c for o in observations for c in o.present_concepts})
    evidence = SceneEvidence(
        observations=observations,
        sampled_count=sampled_count,
        candidate_count=len(observations),
        succeeded_count=len(successful),
        complete_for_selected_frames=len(successful) == len(observations),
        observed_timestamps_ms=sorted({o.timestamp_ms for o in successful}),
        representative_frame_index=representative_frame_index,
        representative_timestamp_ms=representative_timestamp_ms,
        present_concepts=positives,
        temporal_observations=temporal_observations or [],
    )
    metadata = evidence.model_dump()
    metadata.update(
        scene=summary,
        traffic=traffic,
        traffic_control=traffic_control,
        road=road,
        caption=sequence_caption
        if sequence_caption is not None
        else "; ".join(f"{o.timestamp_ms / 1000:g} s: {o.caption}" for o in successful),
        caption_source="vlm_sequence" if sequence_caption is not None else "frame_observations",
        retrieval_tags=sorted(
            {tag for o in successful for tag in o.attributes.get("retrieval_tags", [])}
        ),
        ocr=[item for o in successful for item in o.attributes.get("ocr", [])],
    )
    status = (
        "success"
        if len(successful) == len(observations)
        else "partial"
        if successful
        else "not_configured"
        if all(o.status == "not_configured" for o in observations)
        else "failed"
    )
    return {
        "metadata": metadata,
        "present_concepts": positives,
        "absent_concepts": [],
        "enrichment": {"status": status, "source": "scene_observations"},
    }


def aggregate_scene_metadata(scene: SceneRecord) -> None:
    representative = scene.representative_frame or scene.keyframes[0]
    scene.metadata["vlm_data"] = aggregate_observations(
        [observation_from_frame(f) for f in scene.vlm_candidates or [representative]],
        sampled_count=scene.metadata.get("sampled_frame_count"),
        representative_frame_index=representative.frame_index,
        representative_timestamp_ms=representative.timestamp_ms,
    )


def metadata_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Consistent top-level pushdown fields; null removes stale known values on refresh."""
    metadata = data["metadata"]
    scene = metadata.get("scene", {})
    result = {
        "metadata": metadata,
        "caption": metadata.get("caption", ""),
        "retrieval_tags": metadata.get("retrieval_tags", []),
        "enrichment": data.get("enrichment"),
        "present_concepts": data.get("present_concepts", []),
        "absent_concepts": data.get("absent_concepts", []),
    }
    for target, source in (
        ("weather", "weather"),
        ("timeofday", "time_of_day"),
        ("scene", "scene_type"),
    ):
        value = scene.get(source)
        result[target] = value if value and value != "unknown" else None
    observations = metadata["observations"]
    result["objects"] = sorted({name for o in observations for name in o["objects"]})
    result["behaviors"] = sorted({name for o in observations for name in o["behaviors"]})
    counts: dict[str, int] = {}
    for observation in observations:
        for name, count in observation["object_counts"].items():
            counts[name] = max(counts.get(name, 0), count)
    result["object_counts"] = counts
    return result
