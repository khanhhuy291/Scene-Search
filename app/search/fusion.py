"""Reciprocal Rank Fusion over heterogeneous retrieval signals.

Three signals rank the same candidates on incompatible scales: a cosine
similarity sits in roughly [0.1, 0.4], a metadata match is a fraction in [0, 1],
and a behaviour-window score is on whatever scale the matcher produces. Combining
them by weighted sum requires inventing a normalisation and three coefficients,
and then defending numbers nobody measured.

RRF sidesteps that by discarding the scores entirely and using only *rank*:

    score(d) = sum over signals of  weight_i / (k + rank_i(d))

A document ranked first by any signal contributes 1/(k+1) from it; ranked tenth,
1/(k+10). No calibration, no tuning, and a signal that returns nothing simply
contributes nothing rather than dragging every score toward zero.

``k`` damps the gap between the top few ranks so that one signal cannot dominate
outright. 60 is the conventional value and is kept as the default; it is exposed
so the evaluation can report a sweep rather than assert it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

# Conventional damping constant. Larger flattens the contribution curve; smaller
# makes rank 1 dominate. Swept in the evaluation, not guessed at in a service.
DEFAULT_K = 60


@dataclass(frozen=True)
class RankedList:
    """One signal's opinion, best first.

    ``ids`` must be ordered and free of duplicates. A duplicate would let the
    same document collect the constant twice from one signal, which is the
    quiet version of double-counting.
    """

    signal: str
    ids: Sequence[str]
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.signal:
            raise ValueError("signal must be a non-empty name")
        if self.weight < 0:
            raise ValueError(f"weight must not be negative, got {self.weight}")
        if len(set(self.ids)) != len(self.ids):
            raise ValueError(f"ranked list {self.signal!r} contains duplicate ids")


@dataclass
class FusedResult:
    """One document's fused score and where it came from."""

    id: str
    score: float
    # Per-signal contribution, for `explain=true`. Absent keys mean that signal
    # did not rank this document at all, which is different from ranking it last.
    contributions: dict[str, float] = field(default_factory=dict)
    ranks: dict[str, int] = field(default_factory=dict)


def reciprocal_rank_fusion(
    lists: Iterable[RankedList],
    *,
    k: int = DEFAULT_K,
    limit: int | None = None,
) -> list[FusedResult]:
    """Fuse ranked lists. Returns results ordered best first.

    Ties are broken by id, ascending. Deterministic ordering matters more than it
    looks: without it the same query returns the same set in a different order on
    each call, which makes cursor pagination skip and repeat documents, and makes
    an evaluation run irreproducible.
    """

    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")

    scores: dict[str, float] = {}
    contributions: dict[str, dict[str, float]] = {}
    ranks: dict[str, dict[str, int]] = {}

    for ranked in lists:
        if ranked.weight == 0:
            continue
        for position, doc_id in enumerate(ranked.ids, start=1):
            contribution = ranked.weight / (k + position)
            scores[doc_id] = scores.get(doc_id, 0.0) + contribution
            contributions.setdefault(doc_id, {})[ranked.signal] = contribution
            ranks.setdefault(doc_id, {})[ranked.signal] = position

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        if limit < 0:
            raise ValueError(f"limit must not be negative, got {limit}")
        ordered = ordered[:limit]

    return [
        FusedResult(
            id=doc_id,
            score=score,
            contributions=contributions.get(doc_id, {}),
            ranks=ranks.get(doc_id, {}),
        )
        for doc_id, score in ordered
    ]


def rank_by_metadata_match(
    candidates: Sequence[str],
    matched: Mapping[str, float],
) -> RankedList:
    """Rank candidates by how much soft metadata they matched.

    Soft preferences reorder; they never exclude. A candidate absent from
    ``matched`` scores zero and still appears — it is a preference, not a filter,
    and dropping it here would silently turn one into the other.
    """

    ordered = sorted(candidates, key=lambda doc_id: (-matched.get(doc_id, 0.0), doc_id))
    return RankedList(signal="metadata", ids=ordered)


def rank_by_behavior(
    candidates: Sequence[str],
    scores: Mapping[str, float],
) -> RankedList:
    """Rank candidates by behaviour-window score.

    Only candidates with a score appear. Unlike metadata, a behaviour signal has
    nothing to say about a document with no matching event, and inventing a
    zero-ranked tail would give every unmatched document a contribution it did
    not earn.
    """

    scored = [doc_id for doc_id in candidates if doc_id in scores]
    ordered = sorted(scored, key=lambda doc_id: (-scores[doc_id], doc_id))
    return RankedList(signal="behavior", ids=ordered)


__all__ = [
    "DEFAULT_K",
    "FusedResult",
    "RankedList",
    "rank_by_behavior",
    "rank_by_metadata_match",
    "reciprocal_rank_fusion",
]
