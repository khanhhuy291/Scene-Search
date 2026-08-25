"""Retrieval metrics. Pure functions over ranked id lists — no engine, no index, no IO.

Kept separate from everything else because these are the numbers that go in the
report, and a number in a report has to be checkable by hand. Each one below is
small enough to verify against a worked example, and each test states the example.

Two decisions worth reading before trusting the output.

**precision@k divides by k, not by how many results came back.** That is the
standard definition and the one every published figure uses, so it is the one that
makes our number comparable. But it punishes correct abstention: a query that
honestly returns 3 results, all right, scores P@10 = 0.3. Since abstention is a
*feature* of this system — the similarity floor exists to return nothing rather
than nonsense — :func:`precision_at_k` also reports the shown-precision separately.
Read them together or the floor will look like a regression.

**Relevance is binary.** Nothing here grades "somewhat relevant". The ground truth
available to this project is an object-count predicate over MOT tracks, which is
exactly true or exactly false, and inventing graded relevance on top of a binary
source would be decoration.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PrecisionAtK:
    """Precision at a cutoff, reported two ways.

    ``value`` is the comparable-to-literature number. ``of_shown`` is what a user
    would perceive: of the results actually on screen, how many were right.
    """

    k: int
    value: float
    of_shown: float
    hits: int
    shown: int


def precision_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> PrecisionAtK:
    if k < 1:
        raise ValueError("k must be >= 1")
    truth = set(relevant)
    top = list(ranked[:k])
    hits = sum(1 for item in top if item in truth)
    return PrecisionAtK(
        k=k,
        value=hits / k,
        # An empty result set has no precision to speak of. Zero would say "every
        # result was wrong", which is a different claim from "there were none".
        of_shown=(hits / len(top)) if top else float("nan"),
        hits=hits,
        shown=len(top),
    )


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of all relevant items that appear in the top k.

    The denominator is every relevant item *in the corpus*, which is only knowable
    when ground truth is exhaustive — as it is for the object band, where the MOT
    table lists every frame. When truth comes from pooled judgement instead, the
    denominator is the pool, and the number means "recall against what was
    judged", which is a weaker claim. :mod:`eval.truth` records which of the two
    produced a given denominator so the report can say so.
    """

    truth = set(relevant)
    if not truth:
        # No relevant items means recall is undefined, not perfect. Returning 1.0
        # here would let a query with broken ground truth report a flawless score.
        return float("nan")
    return sum(1 for item in ranked[:k] if item in truth) / len(truth)


def dcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    truth = set(relevant)
    return sum(
        1.0 / math.log2(position + 2) for position, item in enumerate(ranked[:k]) if item in truth
    )


def ndcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """DCG normalised by the best achievable ordering.

    With binary relevance the ideal ranking is simply every relevant item first,
    capped at k *and* at how many relevant items exist — a query with two relevant
    items in the whole corpus can reach 1.0 by putting both at the top, and should
    not be penalised for failing to fill the other eight slots.
    """

    truth = set(relevant)
    if not truth:
        return float("nan")
    ideal_hits = min(len(truth), k)
    ideal = sum(1.0 / math.log2(position + 2) for position in range(ideal_hits))
    if ideal == 0.0:
        return float("nan")
    return dcg_at_k(ranked, truth, k) / ideal


def reciprocal_rank(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    """1/rank of the first relevant result, or 0.0 if none is present.

    Zero rather than NaN on a miss: unlike recall, "the user scrolled the whole
    page and found nothing useful" is a real, meaningful score of zero.
    """

    truth = set(relevant)
    for position, item in enumerate(ranked, start=1):
        if item in truth:
            return 1.0 / position
    return 0.0


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile.

    Nearest-rank rather than interpolated because a latency percentile should be a
    measurement that actually occurred. p95 of a 20-query suite interpolated
    between two samples is a number no request ever took.
    """

    if not values:
        return float("nan")
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")
    ordered = sorted(values)
    rank = math.ceil(fraction * len(ordered))
    return ordered[min(rank, len(ordered)) - 1]


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean that ignores NaN, and is NaN when everything was NaN.

    Bands mix queries whose ground truth is exhaustive with queries whose truth is
    missing. Averaging a NaN in as zero would quietly drag a band's score down and
    read as poor retrieval instead of absent ground truth.
    """

    usable = [v for v in values if not math.isnan(v)]
    if not usable:
        return float("nan")
    return sum(usable) / len(usable)


__all__ = [
    "PrecisionAtK",
    "dcg_at_k",
    "mean",
    "ndcg_at_k",
    "percentile",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
