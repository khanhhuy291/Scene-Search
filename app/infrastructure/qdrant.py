"""Qdrant client lifecycle and scene-collection initialization supporting Named Vectors (SigLIP Visual + BGE-M3 Text)."""

from __future__ import annotations

from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from core.config import get_settings

_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Create and return the process-wide asynchronous Qdrant client."""
    global _client
    if _client is None:
        settings = get_settings().qdrant
        kwargs: dict[str, object] = {
            "api_key": settings.api_key.get_secret_value() if settings.api_key else None,
            "timeout": settings.timeout,
            "prefer_grpc": settings.prefer_grpc,
        }
        if settings.url:
            kwargs["url"] = settings.url
        else:
            kwargs.update(
                host=settings.host,
                port=settings.port,
                grpc_port=settings.grpc_port,
                https=settings.https,
            )
        _client = AsyncQdrantClient(**kwargs)
    return _client


async def init_qdrant_collections(client: AsyncQdrantClient | None = None, force_recreate: bool = False) -> bool:
    """Ensure the Hybrid Scene Collection exists in Qdrant with Named Vectors ('siglip_visual' & 'bge_text')."""
    qdrant = client or get_qdrant_client()
    settings = get_settings().qdrant

    try:
        if await qdrant.collection_exists(settings.collection):
            info = await qdrant.get_collection(settings.collection)
            vectors_config = getattr(info.config.params, "vectors", None)
            
            # Check if existing collection has named vectors 'siglip_visual' and 'bge_text'
            is_valid_named = (
                isinstance(vectors_config, dict)
                and "siglip_visual" in vectors_config
                and "bge_text" in vectors_config
            )
            
            if is_valid_named and not force_recreate:
                return False
            
            logger.info("Recreating Qdrant collection '{collection}' to support Hybrid Named Vectors...", collection=settings.collection)
            await qdrant.delete_collection(settings.collection)

        # Create collection with named vectors for Hybrid Search
        await qdrant.create_collection(
            collection_name=settings.collection,
            vectors_config={
                "siglip_visual": models.VectorParams(
                    size=768,
                    distance=models.Distance.COSINE,
                ),
                "bge_text": models.VectorParams(
                    size=1024,
                    distance=models.Distance.COSINE,
                ),
            },
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=False,
                )
            ),
        )
        logger.info(
            "Created Hybrid Qdrant collection '{collection}' with named vectors 'siglip_visual' (768d) and 'bge_text' (1024d)",
            collection=settings.collection,
        )
        return True
    except Exception:
        logger.exception("Failed to initialize Qdrant collection {collection}", collection=settings.collection)
        raise


async def close_qdrant() -> None:
    """Close the shared Qdrant client."""
    global _client
    client, _client = _client, None
    if client is not None:
        await client.close()


__all__ = ["close_qdrant", "get_qdrant_client", "init_qdrant_collections"]
