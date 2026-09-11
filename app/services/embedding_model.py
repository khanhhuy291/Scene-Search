"""Authenticated API client for the internal Qwen embedding model lifecycle."""

from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from core.config import get_settings
from schemas.admin import EmbeddingModelStatus


def _connection() -> tuple[str, dict[str, str], float]:
    settings = get_settings().ml
    if not settings.qwen_embedding_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qwen embedding endpoint is not configured",
        )
    headers: dict[str, str] = {}
    if settings.qwen_embedding_api_key:
        headers["Authorization"] = f"Bearer {settings.qwen_embedding_api_key.get_secret_value()}"
    return settings.qwen_embedding_url.rstrip("/"), headers, settings.qwen_embedding_timeout


async def embedding_model_request(
    action: str = "status",
) -> EmbeddingModelStatus:
    if action not in {"status", "load", "unload"}:
        raise ValueError(f"Unsupported model action: {action}")
    base_url, headers, timeout = _connection()
    method = "GET" if action == "status" else "POST"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, f"{base_url}/model/{action}", headers=headers)
        response.raise_for_status()
        return EmbeddingModelStatus.model_validate(response.json())
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail")
        except Exception:  # noqa: BLE001 - retain a useful upstream fallback
            detail = None
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail or "Embedding model lifecycle request failed",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qwen embedding service is unavailable",
        ) from exc


async def require_qwen_embedding_ready() -> None:
    model = await embedding_model_request("status")
    if model.state not in {"ready", "busy"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Qwen embedding model is {model.state}; load it before ingesting",
        )


__all__ = ["embedding_model_request", "require_qwen_embedding_ready"]
