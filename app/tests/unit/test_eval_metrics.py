"""Retrieval metrics.

Each test states a worked example, because these numbers end up in a report and a
number in a report has to be checkable by hand. Where a metric returns NaN the
test says why NaN is the right answer rather than zero — that distinction is the
whole reason the harness can report a band as unavailable instead of as bad.
"""

from __future__ import annotations

import math

import pytest

from eval.metrics import (
    dcg_at_k,
    mean,
    ndcg_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RANKED = ["v1", "v2", "v3", "v4", "v5"]
RELEVANT = {"v1", "v3", "v9"}


# -- precision ---------------------------------------------------------------


def test_precision_at_k_divides_by_k() -> None:
    # v1 and v3 are relevant among the first 5 → 2/5.
    assert precision_at_k(RANKED, RELEVANT, 5).value == pytest.approx(0.4)


def test_precision_at_k_still_divides_by_k_when_fewer_results_came_back() -> None:
    # Two results, both right. The comparable number is 2/10, because that is what
    # every published precision@10 means.
    result = precision_at_k(["v1", "v3"], RELEVANT, 10)
    assert result.value == pytest.approx(0.2)
    # And the number a user would recognise is 2/2.
    assert result.of_shown == pytest.approx(1.0)


def test_precision_of_shown_is_not_a_number_when_nothing_was_shown() -> None:
    # Zero would assert that every result was wrong, which is a different claim
    # from there having been none — and correct abstention must not read as a
    # precision failure.
    assert math.isnan(precision_at_k([], RELEVANT, 10).of_shown)


def test_precision_counts_hits_and_shown_for_the_report() -> None:
    result = precision_at_k(RANKED, RELEVANT, 3)
    assert (result.hits, result.shown) == (2, 3)


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError, match="k must be"):
        precision_at_k(RANKED, RELEVANT, 0)


# -- recall ------------------------------------------------------------------


def test_recall_divides_by_every_relevant_item_not_by_what_was_returned() -> None:
    # Three relevant exist in the corpus; two are in the top 5.
    assert recall_at_k(RANKED, RELEVANT, 5) == pytest.approx(2 / 3)


def test_recall_is_not_a_number_when_nothing_is_relevant() -> None:
    # Returning 1.0 would let a query with broken ground truth report a flawless
    # score, which is exactly the failure this harness exists to avoid.
    assert math.isnan(recall_at_k(RANKED, set(), 5))


def test_recall_is_bounded_by_the_cutoff() -> None:
    assert recall_at_k(RANKED, RELEVANT, 1) == pytest.approx(1 / 3)


# -- nDCG --------------------------------------------------------------------


def test_dcg_weights_earlier_positions_more() -> None:
    # 1/log2(2) + 1/log2(4) = 1.0 + 0.5
    assert dcg_at_k(["v1", "x", "v3"], RELEVANT, 3) == pytest.approx(1.5)


def test_ndcg_is_one_when_every_relevant_item_is_at_the_top() -> None:
    assert ndcg_at_k(["v1", "v3", "v9", "x"], RELEVANT, 4) == pytest.approx(1.0)


def test_ndcg_ideal_is_capped_by_how_many_relevant_items_exist() -> None:
    # Two relevant items in the whole corpus, both returned first. That is a
    # perfect answer and must score 1.0 rather than being penalised for leaving
    # eight slots unfilled.
    assert ndcg_at_k(["a", "b", "c"], {"a", "b"}, 10) == pytest.approx(1.0)


def test_ndcg_falls_when_relevant_items_are_ranked_lower() -> None:
    high = ndcg_at_k(["v1", "v3", "x", "y"], RELEVANT, 4)
    low = ndcg_at_k(["x", "y", "v1", "v3"], RELEVANT, 4)
    assert high > low


# -- reciprocal rank ---------------------------------------------------------


def test_reciprocal_rank_is_one_over_the_first_hit() -> None:
    assert reciprocal_rank(["x", "v1"], RELEVANT) == pytest.approx(0.5)


def test_reciprocal_rank_is_zero_when_nothing_relevant_was_found() -> None:
    # Zero rather than NaN: unlike recall, "read the whole page and found nothing"
    # is a real score, and it is the score the user experienced.
    assert reciprocal_rank(["x", "y"], RELEVANT) == 0.0


# -- aggregation -------------------------------------------------------------


def test_mean_ignores_unmeasurable_queries() -> None:
    # A band mixes queries with and without ground truth. Averaging NaN in as zero
    # would read as poor retrieval instead of absent truth.
    assert mean([1.0, float("nan"), 0.0]) == pytest.approx(0.5)


def test_mean_of_nothing_measurable_is_not_a_number() -> None:
    assert math.isnan(mean([float("nan"), float("nan")]))


def test_percentile_returns_an_observed_value() -> None:
    # Nearest-rank, so p95 of a small sample is a latency some request actually
    # had rather than an interpolation between two that did not occur.
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.5) == 20.0
    assert percentile(values, 0.95) == 40.0
    assert percentile(values, 1.0) == 40.0


def test_percentile_of_nothing_is_not_a_number() -> None:
    assert math.isnan(percentile([], 0.5))


def test_percentile_fraction_is_validated() -> None:
    with pytest.raises(ValueError, match="fraction"):
        percentile([1.0], 0.0)
