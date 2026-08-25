"""Opaque pagination cursors for search results.

Offset paging over an approximate nearest-neighbour search is wrong in a way that
is easy to miss: the HNSW traversal is re-run for page two, and because it is
approximate it can return a slightly different candidate set. Documents then
appear on both pages, or on neither. Keyset paging avoids that by carrying the
last position forward instead of counting from the start.

The cursor is opaque to the client but is not a security boundary — it encodes
no identity and grants no access. What it *does* enforce is that a cursor is used
with the query that produced it: a fingerprint of the query and filters travels
inside, and decoding against a different search is rejected. Without that check a
stale cursor from a previous search silently returns results from the wrong
ranking, which looks like a relevance bug rather than a paging bug.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Bumped when the payload shape changes. An old client's cursor then fails
# cleanly instead of being misread as the new shape.
CURSOR_VERSION = 1


class CursorError(ValueError):
    """Raised when a cursor is malformed, or belongs to a different search."""


def fingerprint(query: str, filters: Any = None, *, granularity: str = "segment") -> str:
    """Stable short hash of the search a cursor belongs to.

    Filters are serialised with sorted keys so that two logically identical
    searches produce the same fingerprint regardless of dict ordering.
    """

    if filters is None:
        payload: Any = None
    elif hasattr(filters, "model_dump"):
        payload = filters.model_dump(exclude_none=True)
    else:
        payload = filters

    material = json.dumps(
        {"q": query.strip(), "f": payload, "g": granularity},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Cursor:
    """The position to resume from.

    ``(score, id)`` together, not score alone: fused scores collide often —
    RRF produces the same value for any two documents ranked identically by the
    same signals — and resuming on score alone would drop every tied document
    after the first.
    """

    fingerprint: str
    last_score: float
    last_id: str
    offset: int = 0

    def encode(self) -> str:
        raw = json.dumps(
            {
                "v": CURSOR_VERSION,
                "f": self.fingerprint,
                "s": self.last_score,
                "i": self.last_id,
                "o": self.offset,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        # urlsafe + stripped padding: cursors travel in query strings and JSON,
        # and '=' is noisy in both.
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str, *, expected_fingerprint: str | None = None) -> Cursor:
    """Decode a cursor, rejecting anything that is not ours.

    Raises ``CursorError`` on malformed input and on a fingerprint mismatch. The
    caller should surface that as a client error, not a server error: a bad
    cursor is a bad request.
    """

    if not token:
        raise CursorError("cursor is empty")

    padded = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise CursorError("cursor is not decodable") from exc

    if not isinstance(data, dict):
        raise CursorError("cursor payload is not an object")

    version = data.get("v")
    if version != CURSOR_VERSION:
        raise CursorError(f"cursor version {version!r} is not supported")

    try:
        cursor = Cursor(
            fingerprint=str(data["f"]),
            last_score=float(data["s"]),
            last_id=str(data["i"]),
            offset=int(data.get("o", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CursorError("cursor payload is missing required fields") from exc

    if expected_fingerprint is not None and cursor.fingerprint != expected_fingerprint:
        raise CursorError(
            "cursor belongs to a different query or filter set; start again from the first page"
        )
    return cursor


def next_cursor(
    results: list[Any],
    *,
    query: str,
    filters: Any = None,
    granularity: str = "segment",
    offset: int = 0,
) -> str | None:
    """Build the cursor for the page after ``results``, or None if it is the last.

    ``results`` are the fused results already sliced to the page size. An empty
    page has no successor, so it returns None rather than a cursor that would
    resume from nowhere.
    """

    if not results:
        return None
    last = results[-1]
    return Cursor(
        fingerprint=fingerprint(query, filters, granularity=granularity),
        last_score=float(last.score),
        last_id=str(last.id),
        offset=offset + len(results),
    ).encode()


def apply_cursor(results: list[Any], cursor: Cursor | None) -> list[Any]:
    """Drop everything up to and including the cursor position.

    Assumes ``results`` are in the same deterministic order the cursor was minted
    from — fused score descending, id ascending as the tie-break. That ordering
    guarantee is what makes keyset paging correct here, and it is why the fusion
    step sorts by ``(-score, id)`` rather than by score alone.
    """

    if cursor is None:
        return results
    for position, item in enumerate(results):
        score = float(item.score)
        if (score < cursor.last_score) or (
            score == cursor.last_score and str(item.id) > cursor.last_id
        ):
            return results[position:]
    return []


__all__ = [
    "CURSOR_VERSION",
    "Cursor",
    "CursorError",
    "apply_cursor",
    "decode_cursor",
    "fingerprint",
    "next_cursor",
]
