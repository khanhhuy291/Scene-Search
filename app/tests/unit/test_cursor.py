"""Opaque pagination cursors.

The properties worth asserting are the ones whose absence produces a *silent*
bug: a cursor reused across queries, a tie dropped at a page boundary, and a
tampered token accepted.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import pytest

from schemas.search import SearchFilters
from search.cursor import (
    CURSOR_VERSION,
    Cursor,
    CursorError,
    apply_cursor,
    decode_cursor,
    fingerprint,
    next_cursor,
)


@dataclass
class _Result:
    id: str
    score: float


def _cursor(fp: str = "abc", score: float = 0.5, doc_id: str = "d") -> Cursor:
    return Cursor(fingerprint=fp, last_score=score, last_id=doc_id)


# --- fingerprint -------------------------------------------------------------


def test_same_search_yields_the_same_fingerprint() -> None:
    a = fingerprint("rainy weather", SearchFilters(weather=["rainy"]))
    b = fingerprint("rainy weather", SearchFilters(weather=["rainy"]))
    assert a == b


def test_whitespace_around_the_query_does_not_change_the_fingerprint() -> None:
    assert fingerprint("  rain  ") == fingerprint("rain")


def test_different_filters_yield_different_fingerprints() -> None:
    # Without this, a cursor from a filtered search would be accepted by an
    # unfiltered one and resume into an entirely different ranking.
    assert fingerprint("rain", SearchFilters(weather=["rainy"])) != fingerprint("rain")


def test_granularity_is_part_of_the_fingerprint() -> None:
    # Frames and segments are different result sets from one collection.
    assert fingerprint("rain", granularity="frame") != fingerprint("rain", granularity="segment")


def test_plain_dict_filters_are_accepted() -> None:
    filters = {"weather": ["rainy"]}
    assert fingerprint("rain", filters) == fingerprint("rain", dict(filters))


# --- round trip --------------------------------------------------------------


def test_cursor_round_trips() -> None:
    original = _cursor(score=0.0491, doc_id="segment-7")
    restored = decode_cursor(original.encode())
    assert restored == original


def test_encoded_cursor_is_url_safe_and_unpadded() -> None:
    token = _cursor().encode()
    assert "=" not in token and "+" not in token and "/" not in token


def test_cursor_from_a_different_query_is_rejected() -> None:
    token = _cursor(fp="query-one").encode()
    with pytest.raises(CursorError, match="different query"):
        decode_cursor(token, expected_fingerprint="query-two")


def test_matching_fingerprint_is_accepted() -> None:
    token = _cursor(fp="same").encode()
    assert decode_cursor(token, expected_fingerprint="same").last_id == "d"


# --- malformed input ---------------------------------------------------------


def test_garbage_is_rejected_rather_than_misread() -> None:
    for token in ("!!!!", "not-base64-@@", base64.urlsafe_b64encode(b"[]").decode()):
        with pytest.raises(CursorError):
            decode_cursor(token)


def test_empty_cursor_is_rejected() -> None:
    with pytest.raises(CursorError, match="empty"):
        decode_cursor("")


def test_a_future_version_fails_cleanly() -> None:
    # An old client must get a clear error, not have its payload misread as the
    # current shape.
    raw = json.dumps({"v": CURSOR_VERSION + 1, "f": "x", "s": 1.0, "i": "a", "o": 0})
    token = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    with pytest.raises(CursorError, match="version"):
        decode_cursor(token)


def test_missing_fields_are_rejected() -> None:
    raw = json.dumps({"v": CURSOR_VERSION, "f": "x"})
    token = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    with pytest.raises(CursorError, match="missing required fields"):
        decode_cursor(token)


# --- paging behaviour --------------------------------------------------------


def test_apply_cursor_resumes_after_the_recorded_position() -> None:
    page = [_Result("a", 0.9), _Result("b", 0.8), _Result("c", 0.7)]
    remaining = apply_cursor(page, _cursor(score=0.8, doc_id="b"))
    assert [r.id for r in remaining] == ["c"]


def test_ties_are_split_by_id_not_dropped() -> None:
    # RRF produces identical scores constantly. Resuming on score alone would
    # discard every tied document after the first — silently losing results.
    page = [_Result("a", 0.5), _Result("b", 0.5), _Result("c", 0.5)]
    remaining = apply_cursor(page, _cursor(score=0.5, doc_id="a"))
    assert [r.id for r in remaining] == ["b", "c"]


def test_no_cursor_returns_the_whole_page() -> None:
    page = [_Result("a", 0.9)]
    assert apply_cursor(page, None) == page


def test_a_cursor_past_the_end_yields_nothing() -> None:
    page = [_Result("a", 0.9), _Result("b", 0.8)]
    assert apply_cursor(page, _cursor(score=0.1, doc_id="z")) == []


def test_next_cursor_is_none_on_an_empty_page() -> None:
    # An empty page has no successor; returning a cursor would invite a request
    # that resumes from nowhere.
    assert next_cursor([], query="rain") is None


def test_next_cursor_points_at_the_last_row_and_carries_the_offset() -> None:
    page = [_Result("a", 0.9), _Result("b", 0.8)]
    token = next_cursor(page, query="rain", offset=20)
    decoded = decode_cursor(token, expected_fingerprint=fingerprint("rain"))
    assert (decoded.last_id, decoded.last_score, decoded.offset) == ("b", 0.8, 22)


def test_paging_end_to_end_visits_every_row_exactly_once() -> None:
    rows = [_Result(f"d{i:02d}", 1.0 - i / 100) for i in range(10)]
    seen: list[str] = []
    cursor = None
    for _ in range(5):
        page = apply_cursor(rows, cursor)[:3]
        if not page:
            break
        seen.extend(r.id for r in page)
        token = next_cursor(page, query="q")
        cursor = decode_cursor(token, expected_fingerprint=fingerprint("q"))

    assert seen == [r.id for r in rows]
    assert len(seen) == len(set(seen))
