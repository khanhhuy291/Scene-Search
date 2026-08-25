"""Qdrant client lifecycle and scene-collection initialization."""

from __future__ import annotations

from typing import Any

from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from core.config import get_settings

_client: AsyncQdrantClient | None = None

# Filters must be evaluated inside Qdrant so that a narrow filter prunes the HNSW
# search instead of discarding results after it. Without these indexes a filtered
# query degrades to a full scan of the collection.
_PAYLOAD_INDEXES: dict[str, models.PayloadSchemaType] = {
    "video_id": models.PayloadSchemaType.KEYWORD,
    "frame_id": models.PayloadSchemaType.KEYWORD,
    "present_concepts": models.PayloadSchemaType.KEYWORD,
    "absent_concepts": models.PayloadSchemaType.KEYWORD,
    "metadata.scene.scene_type": models.PayloadSchemaType.KEYWORD,
    "metadata.scene.time_of_day": models.PayloadSchemaType.KEYWORD,
    "metadata.scene.weather": models.PayloadSchemaType.KEYWORD,
    "metadata.scene.road_surface": models.PayloadSchemaType.KEYWORD,
    "metadata.scene.traffic_density": models.PayloadSchemaType.KEYWORD,
    "metadata.retrieval_tags": models.PayloadSchemaType.KEYWORD,
    "dataset": models.PayloadSchemaType.KEYWORD,
    "split": models.PayloadSchemaType.KEYWORD,
    "weather": models.PayloadSchemaType.KEYWORD,
    "timeofday": models.PayloadSchemaType.KEYWORD,
    "scene": models.PayloadSchemaType.KEYWORD,
    "objects": models.PayloadSchemaType.KEYWORD,
    "behaviors": models.PayloadSchemaType.KEYWORD,
    "granularity": models.PayloadSchemaType.KEYWORD,
    "model_version": models.PayloadSchemaType.KEYWORD,
    "ts_start_s": models.PayloadSchemaType.FLOAT,
    "ts_end_s": models.PayloadSchemaType.FLOAT,
}


def get_qdrant_client() -> AsyncQdrantClient:
    """Create and return the process-wide asynchronous Qdrant client."""

    global _client
    if _client is None:
        settings = get_settings().qdrant
        api_key = settings.api_key.get_secret_value() if settings.api_key else None
        common: dict[str, Any] = {
            "api_key": api_key,
            "timeout": settings.timeout,
            "prefer_grpc": settings.prefer_grpc,
            "check_compatibility": False,
        }
        if settings.url:
            _client = AsyncQdrantClient(url=settings.url, **common)
        else:
            _client = AsyncQdrantClient(
                host=settings.host,
                port=settings.port,
                grpc_port=settings.grpc_port,
                https=settings.https,
                **common,
            )
    return _client


def is_read_only_collection(vectors: object) -> bool:
    """True when the collection is one this process must never write to.

    Public because the write path needs it too: `search.index` refuses to
    upsert or delete against a collection matching this shape.
    """

    return _is_hybrid_named_vectors(vectors)


def _is_hybrid_named_vectors(vectors: object) -> bool:
    """Remote indexes that store named vectors (e.g. qwen, siglip)."""
    if not isinstance(vectors, dict):
        return False
    names = set(vectors)
    return len(names) >= 2 or "qwen" in names


def _validate_collection_config(config: object, expected_size: int) -> None:
    params = getattr(config, "params", None)
    vectors = getattr(params, "vectors", None)
    if _is_hybrid_named_vectors(vectors):
        logger.warning(
            "Qdrant collection uses hybrid named vectors "
            "({names}); attaching without local schema rewrite",
            names=", ".join(sorted(vectors)),
        )
        return

    if isinstance(vectors, dict):
        matching = [
            v
            for v in vectors.values()
            if getattr(v, "size", None) == expected_size
            and getattr(v, "distance", None) == models.Distance.COSINE
        ]
        if not matching:
            raise RuntimeError(
                "Incompatible Qdrant collection named vectors: no vector matches "
                f"size={expected_size}, distance=Cosine"
            )
        return

    size = getattr(vectors, "size", None)
    distance = getattr(vectors, "distance", None)
    if size != expected_size or distance != models.Distance.COSINE:
        raise RuntimeError(
            "Incompatible Qdrant scenes collection: "
            f"expected size={expected_size}, distance=Cosine; got size={size}, distance={distance}"
        )

    quantization = getattr(config, "quantization_config", None)
    scalar = getattr(quantization, "scalar", None)
    if scalar is not None and getattr(scalar, "type", None) != models.ScalarType.INT8:
        raise RuntimeError(
            "Incompatible Qdrant scenes collection: int8 scalar quantization "
            "is required when enabled"
        )


async def ensure_payload_indexes(client: AsyncQdrantClient | None = None) -> list[str]:
    """Create the payload indexes used for metadata prefiltering.

    Idempotent: Qdrant rejects a duplicate index, which is treated as success.
    Returns the field names that were newly created.
    """

    qdrant = client or get_qdrant_client()
    collection = get_settings().qdrant.collection

    created: list[str] = []
    for field_name, schema in _PAYLOAD_INDEXES.items():
        try:
            await qdrant.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=schema,
                wait=True,
            )
            created.append(field_name)
        except Exception as exc:  # noqa: PERF203 - per-field handling is intentional
            # An already-present index is the expected steady state; anything
            # else is a real failure and must not be swallowed.
            if "already exists" in str(exc).lower():
                continue
            logger.exception(
                "Failed to create Qdrant payload index {field} on {collection}",
                field=field_name,
                collection=collection,
            )
            raise
    if created:
        logger.info(
            "Created {count} Qdrant payload indexes on {collection}: {fields}",
            count=len(created),
            collection=collection,
            fields=", ".join(created),
        )
    return created


async def init_qdrant_collections(client: AsyncQdrantClient | None = None) -> bool:
    """Ensure the scene-vector collection and its payload indexes exist.

    The collection uses cosine distance at the configured dimension with int8
    scalar quantization. Returns ``True`` when created and ``False`` when an
    existing, compatible collection was found.
    """

    qdrant = client or get_qdrant_client()
    settings = get_settings().qdrant

    try:
        if await qdrant.collection_exists(settings.collection):
            info = await qdrant.get_collection(settings.collection)
            vectors = getattr(getattr(info.config, "params", None), "vectors", None)
            _validate_collection_config(info.config, settings.vector_size)
            # Do not rewrite payload indexes on a remote hybrid collection —
            # those fields and the search contract belong to Huy's embedder path.
            if _is_hybrid_named_vectors(vectors):
                return False
            await ensure_payload_indexes(qdrant)
            return False

        await qdrant.create_collection(
            collection_name=settings.collection,
            vectors_config=models.VectorParams(
                size=settings.vector_size,
                distance=models.Distance.COSINE,
            ),
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=False,
                )
            ),
        )
        logger.info(
            "Created Qdrant collection {collection} with {dimensions} dimensions",
            collection=settings.collection,
            dimensions=settings.vector_size,
        )
        await ensure_payload_indexes(qdrant)
        return True
    except Exception:
        logger.exception(
            "Failed to initialize Qdrant collection {collection}", collection=settings.collection
        )
        raise


async def close_qdrant() -> None:
    """Close the shared Qdrant client."""

    global _client
    client, _client = _client, None
    if client is not None:
        await client.close()


__all__ = [
    "is_read_only_collection",
    "close_qdrant",
    "ensure_payload_indexes",
    "get_qdrant_client",
    "init_qdrant_collections",
]
