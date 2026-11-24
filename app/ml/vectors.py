"""Validation shared by model boundaries and vector persistence."""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence


def normalize_vectors(
    vectors: Sequence[Sequence[float]], *, dimension: int, count: int | None = None
) -> list[list[float]]:
    if count is not None and len(vectors) != count:
        raise ValueError(f"Encoder returned {len(vectors)} vectors for {count} inputs")
    result = []
    for vector in vectors:
        if len(vector) != dimension:
            raise ValueError(f"Vector dimension {len(vector)} does not match {dimension}")
        values = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Vector contains non-finite values")
        norm = math.hypot(*values)
        if not math.isfinite(norm) or norm <= sys.float_info.epsilon:
            raise ValueError("Vector has zero or invalid norm")
        result.append([value / norm for value in values])
    return result
