"""Verify observations without turning missing metadata into negative evidence."""

from dataclasses import replace

from schemas.search import SearchFilters
from search.attributes import color_relations, relation_polarity, unresolved_colors
from search.catalog import Keyframe
from search.query import CaptionVerdict, ParsedQuery
from search.scene_evidence import evaluate_scene


def verify_chunk(
    frame: Keyframe, parsed: ParsedQuery, filters: SearchFilters | None, *, strict: bool
) -> CaptionVerdict | None:
    bindings = color_relations(parsed.embedding_text)
    unresolved = tuple(
        f"unresolved_color:{color}" for color in unresolved_colors(parsed.embedding_text)
    )
    if strict and unresolved:
        return None
    unknown = (
        *parsed.required,
        *(binding.label for binding in bindings),
        *parsed.excluded,
        *unresolved,
    )
    hard_filters = filters and any(
        (
            filters.weather,
            filters.timeofday,
            filters.scene,
            filters.objects_any,
            filters.objects_all,
            filters.min_object_counts,
            filters.behaviors,
        )
    )
    evidence = frame.evidence
    if evidence is None:
        return None if strict or hard_filters else CaptionVerdict(True, unknown=tuple(unknown))
    if set(evidence.present_concepts).intersection(parsed.excluded):
        return None
    successful = [
        observation for observation in evidence.observations if observation.status == "success"
    ]
    if not successful:
        return None if strict or hard_filters else CaptionVerdict(True, unknown=tuple(unknown))
    eligible = []
    for observation in successful:
        scene = observation.attributes.get("scene", {})
        if filters and any(
            values and scene.get(field) not in values
            for field, values in (
                ("weather", filters.weather),
                ("time_of_day", filters.timeofday),
                ("scene_type", filters.scene),
            )
        ):
            continue
        polarities = [relation_polarity(observation.caption, binding) for binding in bindings]
        if "absent" in polarities or (strict and "unknown" in polarities):
            continue
        eligible.append(observation)
    if not eligible:
        return None
    verdict = evaluate_scene(
        evidence.model_copy(update={"observations": eligible}),
        parsed,
        strict=strict,
        filters=filters,
    )
    if verdict is None:
        return None
    best = next(
        (
            observation
            for observation in eligible
            if observation.timestamp_ms in verdict.matching_timestamps_ms
        ),
        eligible[0],
    )
    unknown_relations = tuple(
        binding.label
        for binding in bindings
        if relation_polarity(best.caption, binding) == "unknown"
    )
    unknown_exclusions = tuple(
        concept for concept in parsed.excluded if concept not in best.absent_concepts
    )
    return replace(
        verdict,
        unknown=(*verdict.unknown, *unknown_relations, *unknown_exclusions, *unresolved),
        matching_timestamps_ms=()
        if verdict.unknown or unknown_relations or unresolved
        else verdict.matching_timestamps_ms,
    )
