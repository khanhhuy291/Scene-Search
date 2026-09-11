"""Qdrant write path: upsert, delete, and count scene points.

The read path (``search.points``) and the write path live side by side and are
owned together, because they share one contract: a point written with a payload
shape the filter builder does not expect is not a runtime error, it is a filter
that silently matches nothing.

Deletion by video is not a convenience. Re-ingesting a video overwrites its
points only where the derived point ids collide; frames dropped by a changed
near-duplicate threshold, or segments that regrouped, leave orphans behind.
Those orphans still match queries and then hydrate against Postgres rows that no
longer exist, which surfaces as results that intermittently vanish rather than
as an error. Delete first, then upsert.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from loguru import logger

from core.config import get_settings
from infrastructure.qdrant import get_qdrant_client
from search.points import Granularity, build_filter

# Chosen so a full 50-video corpus is a few hundred requests rather than tens of
# thousands. Larger batches mostly trade request count for peak memory in the
# client's serializer; 256 x 768 float32 is about 750 KB on the wire.
DEFAULT_BATCH_SIZE = 256


def _collection() -> str:
    return get_settings().qdrant.collection


def _check_dimension(points: Sequence[Any]) -> None:
    """Fail fast when the encoder and the collection disagree."""
    if not points:
        return

    expected = get_settings().qdrant.vector_size
    vector = getattr(points[0], "vector", None)
    if vector is None:
        return

    if isinstance(vector, dict):
        for name, vec in vector.items():
            actual = len(vec) if vec is not None else 0
            if actual and actual not in (768, 2048):
                raise ValueError(
                    f"Named vector {name} dimension {actual} is not supported (expected 768 or 2048)."
                )
        return

    actual = len(vector) if vector is not None else 0
    if actual and actual != expected and actual not in (768, 2048):
        raise ValueError(
            f"Vector dimension {actual} does not match QDRANT_VECTOR_SIZE {expected}. "
            "The encoder and the collection disagree: either ML_ENCODER_NAME changed "
            "without rebuilding the collection, or two encoders are in use."
        )


async def _refuse_if_read_only(qdrant: Any) -> None:
    """Refuse to write to a collection this process did not create.

    The read path attaches to a collection built by another workstream, whose
    layout is two named vectors. Writing into it is never correct from here: the
    embeddings are theirs, and this process cannot produce the second tower at all.

    A convention was not enough. `build_point` has twice been changed to emit a
    named vector to "match" that collection, and both times the name matched
    neither it nor the one this service creates. The second time it was worse than
    a failed write, because `reindex_video` deletes before it upserts and the
    dimension check runs after the delete -- so every reindex became a pure
    deletion against the shared index. This makes that structurally impossible
    rather than something the next reader has to know.
    """

    from infrastructure.qdrant import is_read_only_collection

    collection = _collection()
    try:
        info = await qdrant.get_collection(collection)
    except Exception:  # noqa: BLE001 - an unreachable collection is the caller's problem
        return
    vectors = getattr(getattr(info.config, "params", None), "vectors", None)
    if isinstance(vectors, dict) and is_read_only_collection(vectors):
        settings = get_settings().qdrant
        if settings.allow_named_vector_writes:
            collection_names = set(vectors)
            if "qwen" in collection_names and "bgem3" not in collection_names:
                return
            if settings.write_vector_name and settings.write_vector_name in collection_names:
                return
        selected = vectors.get(settings.write_vector_name)
        if (
            settings.write_vector_name
            and selected is not None
            and getattr(selected, "size", None) == settings.vector_size
        ):
            return
        raise RuntimeError(
            f"Refusing to write to {collection!r}: it uses the hybrid named-vector "
            f"layout ({', '.join(sorted(vectors))}) built by another workstream. "
            "This process attaches to that collection read-only. Point "
            "QDRANT_COLLECTION at a collection this service owns before ingesting."
        )


async def upsert_points(
    points: Sequence[Any],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    client: Any | None = None,
) -> int:
    """Upsert scene points in batches. Returns the number written.

    Build points with :func:`search.points.build_point` rather than constructing
    them here: it derives a deterministic id from ``(granularity, entity_id)``,
    which is what makes re-indexing overwrite instead of duplicate.

    ``wait=True`` on every batch. Ingestion is offline work where a few
    milliseconds per batch costs nothing, and the alternative is an integration
    test that counts points before the write is visible and fails intermittently.
    """

    if not points:
        return 0
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")

    settings = get_settings().qdrant
    if settings.write_vector_name:

        def _wrap_named_vector(p: Any) -> Any:
            v = getattr(p, "vector", None)
            if v is not None and not isinstance(v, dict):
                if hasattr(p, "model_copy"):
                    return p.model_copy(update={"vector": {settings.write_vector_name: v}})
                if hasattr(p, "__dict__"):
                    p.vector = {settings.write_vector_name: v}
            return p

        points = [_wrap_named_vector(point) for point in points]
    _check_dimension(points)

    qdrant = client or get_qdrant_client()
    await _refuse_if_read_only(qdrant)
    collection = _collection()

    written = 0
    for start in range(0, len(points), batch_size):
        batch = points[start : start + batch_size]
        await qdrant.upsert(collection_name=collection, points=list(batch), wait=True)
        written += len(batch)

    logger.info(
        "Upserted {written} points into {collection} in {batches} batch(es)",
        written=written,
        collection=collection,
        batches=(len(points) + batch_size - 1) // batch_size,
    )
    return written


async def delete_by_video(
    video_id: str,
    *,
    client: Any | None = None,
) -> None:
    """Delete every point belonging to a video, at both granularities.

    Deliberately not constrained by ``granularity``: a video owns both its frame
    points and its segment points, and deleting only one kind would leave the
    other pointing at rows the caller is about to replace.
    """

    if not video_id:
        raise ValueError("video_id must not be empty")

    from qdrant_client.http import models

    qdrant = client or get_qdrant_client()
    await _refuse_if_read_only(qdrant)
    collection = _collection()

    # Reuse the read path's filter builder so there is exactly one place that
    # knows how a video_id condition is expressed.
    condition = build_filter(video_ids=[video_id])

    await qdrant.delete(
        collection_name=collection,
        points_selector=models.FilterSelector(filter=condition),
        wait=True,
    )
    logger.info(
        "Deleted all points for video {video_id} from {collection}",
        video_id=video_id,
        collection=collection,
    )


async def count_points(
    *,
    granularity: Granularity | None = None,
    video_id: str | None = None,
    client: Any | None = None,
) -> int:
    """Count points, optionally narrowed by granularity or video.

    Used by the integration check that ``frames + segments == points``. An exact
    count is requested because an approximate one makes that assertion flaky for
    no benefit at this corpus size.
    """

    qdrant = client or get_qdrant_client()
    condition = build_filter(
        granularity=granularity,
        video_ids=[video_id] if video_id else None,
    )
    result = await qdrant.count(
        collection_name=_collection(),
        count_filter=condition,
        exact=True,
    )
    count = getattr(result, "count", result)
    if isinstance(count, int):
        return count
    raise TypeError(f"Qdrant count() returned {type(result)!r}, expected an integer count")


async def reindex_video(
    video_id: str,
    points: Sequence[Any],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    client: Any | None = None,
) -> int:
    """Replace a video's points: delete, then upsert.

    The order matters and the obvious alternative is wrong. Upserting first and
    deleting after would remove the points just written, because the delete
    filter matches on ``video_id`` and cannot distinguish old points from new.
    """

    qdrant = client or get_qdrant_client()
    await delete_by_video(video_id, client=qdrant)
    return await upsert_points(points, batch_size=batch_size, client=qdrant)


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "count_points",
    "delete_by_video",
    "reindex_video",
    "upsert_points",
]
