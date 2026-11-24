"""One evidence policy for catalog and freshly retrieved scene candidates."""

from schemas.scene_evidence import SceneEvidence, SceneObservation
from schemas.search import SearchFilters
from search.query import CaptionVerdict, ParsedQuery, Polarity


def scene_polarity(evidence: SceneEvidence, concept: str) -> Polarity:
    # Sparse explicit negatives remain scoped to their observations.
    return "present" if concept in evidence.present_concepts else "unknown"


def observation_matches(observation: SceneObservation, filters: SearchFilters | None) -> bool:
    if filters is None:
        return True
    objects = {name.casefold() for name in observation.objects}
    if filters.objects_any and objects.isdisjoint(name.casefold() for name in filters.objects_any):
        return False
    if filters.objects_all and not {name.casefold() for name in filters.objects_all} <= objects:
        return False
    counts = {name.casefold(): count for name, count in observation.object_counts.items()}
    if any(
        counts.get(name.casefold(), 0) < count
        for name, count in (filters.min_object_counts or {}).items()
    ):
        return False
    return not (
        filters.behaviors
        and {b.casefold() for b in observation.behaviors}.isdisjoint(
            b.casefold() for b in filters.behaviors
        )
    )


def evaluate_scene(
    evidence: SceneEvidence,
    parsed: ParsedQuery,
    *,
    strict: bool,
    filters: SearchFilters | None = None,
) -> CaptionVerdict | None:
    positives = set(evidence.present_concepts)
    if positives.intersection(parsed.excluded):
        return None
    required = set(parsed.required)
    # Even non-strict mode cannot combine known positives from different frames.
    needed = required if strict else required & positives
    eligible = [
        o
        for o in evidence.observations
        if needed <= set(o.present_concepts) and observation_matches(o, filters)
    ]
    if not eligible:
        return None
    best = max(eligible, key=lambda o: len(required.intersection(o.present_concepts)))
    confirmed = tuple(c for c in parsed.required if c in best.present_concepts)
    return CaptionVerdict(admissible=True, confirmed=confirmed, denied=(), mentions=len(confirmed))
