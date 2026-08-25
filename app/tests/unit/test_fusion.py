"""Reciprocal Rank Fusion.

What matters here is not that the arithmetic is right — it is four lines — but
that the properties the rest of the search path depends on hold: deterministic
ordering, graceful degradation when a signal is empty, and no double counting.
"""

from __future__ import annotations

import pytest

from search.fusion import (
    DEFAULT_K,
    RankedList,
    rank_by_behavior,
    rank_by_metadata_match,
    reciprocal_rank_fusion,
)


def test_rank_one_beats_rank_two_from_the_same_signal() -> None:
    fused = reciprocal_rank_fusion([RankedList("dense", ["a", "b", "c"])])
    assert [r.id for r in fused] == ["a", "b", "c"]
    assert fused[0].score == pytest.approx(1 / (DEFAULT_K + 1))


def test_agreement_across_signals_outranks_a_single_first_place() -> None:
    # The point of fusing: something every signal likes should beat something
    # one signal adores and the others have never heard of.
    fused = reciprocal_rank_fusion(
        [
            RankedList("dense", ["loner", "agreed"]),
            RankedList("metadata", ["agreed", "other"]),
            RankedList("behavior", ["agreed"]),
        ]
    )
    assert fused[0].id == "agreed"


def test_an_empty_signal_contributes_nothing_and_does_not_break_ranking() -> None:
    # A behaviour signal with no matching events is normal, not an error. It must
    # not drag every score toward zero or reorder the remaining signals.
    with_empty = reciprocal_rank_fusion(
        [RankedList("dense", ["a", "b"]), RankedList("behavior", [])]
    )
    without = reciprocal_rank_fusion([RankedList("dense", ["a", "b"])])
    assert [r.id for r in with_empty] == [r.id for r in without]
    assert with_empty[0].score == pytest.approx(without[0].score)


def test_ordering_is_deterministic_for_tied_scores() -> None:
    # Ties are common: RRF gives identical values to documents ranked identically.
    # Without a stable tie-break, cursor paging skips and repeats rows, and two
    # evaluation runs disagree for no reason.
    lists = [RankedList("dense", ["z", "y", "x"])]
    first = reciprocal_rank_fusion([RankedList("dense", ["b", "a"])])
    second = reciprocal_rank_fusion([RankedList("dense", ["b", "a"])])
    assert [r.id for r in first] == [r.id for r in second]

    tied = reciprocal_rank_fusion([RankedList("s1", ["p", "q"]), RankedList("s2", ["q", "p"])])
    assert [r.id for r in tied] == ["p", "q"]  # equal scores, id ascending
    assert tied[0].score == pytest.approx(tied[1].score)
    assert reciprocal_rank_fusion(lists)[0].id == "z"


def test_contributions_and_ranks_are_reported_per_signal() -> None:
    # This is what `explain=true` serves. A reviewer needs to see which signal
    # carried a result, not just that it scored well.
    fused = reciprocal_rank_fusion([RankedList("dense", ["a"]), RankedList("behavior", ["a"])])
    assert set(fused[0].contributions) == {"dense", "behavior"}
    assert fused[0].ranks == {"dense": 1, "behavior": 1}


def test_absent_from_a_signal_is_not_the_same_as_ranked_last() -> None:
    fused = reciprocal_rank_fusion([RankedList("dense", ["a", "b"]), RankedList("behavior", ["a"])])
    by_id = {r.id: r for r in fused}
    assert "behavior" in by_id["a"].contributions
    assert "behavior" not in by_id["b"].contributions


def test_weights_scale_a_signal_and_zero_disables_it() -> None:
    boosted = reciprocal_rank_fusion(
        [RankedList("dense", ["a"]), RankedList("behavior", ["b"], weight=3.0)]
    )
    assert boosted[0].id == "b"

    disabled = reciprocal_rank_fusion(
        [RankedList("dense", ["a"]), RankedList("behavior", ["b"], weight=0.0)]
    )
    assert [r.id for r in disabled] == ["a"]


def test_duplicate_ids_in_one_list_are_rejected() -> None:
    # A duplicate lets one signal pay the constant twice for the same document.
    with pytest.raises(ValueError, match="duplicate"):
        RankedList("dense", ["a", "a"])


def test_limit_truncates_after_ranking_not_before() -> None:
    fused = reciprocal_rank_fusion([RankedList("dense", ["a", "b", "c", "d"])], limit=2)
    assert [r.id for r in fused] == ["a", "b"]


def test_invalid_arguments_are_rejected() -> None:
    with pytest.raises(ValueError, match="k must be"):
        reciprocal_rank_fusion([RankedList("dense", ["a"])], k=0)
    with pytest.raises(ValueError, match="limit"):
        reciprocal_rank_fusion([RankedList("dense", ["a"])], limit=-1)
    with pytest.raises(ValueError, match="weight"):
        RankedList("dense", ["a"], weight=-1.0)
    with pytest.raises(ValueError, match="signal"):
        RankedList("", ["a"])


def test_no_lists_yields_no_results() -> None:
    assert reciprocal_rank_fusion([]) == []


# --- signal builders ---------------------------------------------------------


def test_metadata_ranking_keeps_unmatched_candidates() -> None:
    # Soft preferences reorder; they never exclude. Dropping unmatched candidates
    # here would silently turn a preference into a filter.
    ranked = rank_by_metadata_match(["a", "b", "c"], {"b": 1.0, "a": 0.5})
    assert ranked.ids == ["b", "a", "c"]


def test_behavior_ranking_omits_candidates_with_no_event() -> None:
    # Unlike metadata, a behaviour signal has nothing to say about a document
    # with no matching event; a zero-ranked tail would hand every unmatched
    # document a contribution it did not earn.
    ranked = rank_by_behavior(["a", "b", "c"], {"c": 0.9, "a": 0.2})
    assert ranked.ids == ["c", "a"]
