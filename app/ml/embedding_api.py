"""Internal HTTP service hosting one Qwen3-VL embedding model on the GPU."""

from __future__ import annotations

import asyncio
import base64
import binascii
import gc
import io
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, status
from loguru import logger
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator

from core.config import get_settings
from ml.qwen_encoder import QwenEmbeddingError, get_qwen_embedding_client

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_BATCH_SIZE = 16
_inference_lock = threading.Lock()
_state_lock = threading.Lock()
_state = "unloaded"
_last_error: str | None = None
_active_requests = 0


class ModelNotReadyError(RuntimeError):
    """Raised when inference is requested before the model is loaded."""


class ModelBusyError(RuntimeError):
    """Raised when unloading would interrupt an active operation."""


class EmbeddingRequest(BaseModel):
    mode: Literal["text", "image", "multimodal"]
    texts: list[str] = Field(default_factory=list, max_length=MAX_BATCH_SIZE)
    images: list[str] = Field(default_factory=list, max_length=MAX_BATCH_SIZE)

    @model_validator(mode="after")
    def validate_inputs(self) -> EmbeddingRequest:
        if self.mode == "text" and (not self.texts or self.images):
            raise ValueError("text mode requires texts and does not accept images")
        if self.mode == "image" and (not self.images or self.texts):
            raise ValueError("image mode requires images and does not accept texts")
        if self.mode == "multimodal" and (
            not self.images or len(self.images) != len(self.texts)
        ):
            raise ValueError("multimodal mode requires equally sized images and texts")
        if any(not text.strip() for text in self.texts):
            raise ValueError("texts must not contain empty values")
        return self


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimension: int


class ModelStatusResponse(BaseModel):
    state: Literal["unloaded", "loading", "ready", "busy", "unloading", "error"]
    model: str
    dimension: int
    error: str | None = None
    gpu_memory_allocated_mb: float | None = None
    gpu_memory_reserved_mb: float | None = None


def _authorize(authorization: str | None, x_api_key: str | None) -> None:
    configured = get_settings().ml.qwen_embedding_api_key
    if configured is None:
        return
    expected = configured.get_secret_value()
    bearer = authorization.removeprefix("Bearer ") if authorization else None
    if bearer != expected and x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def _decode_images(values: list[str]) -> list[Image.Image]:
    decoded: list[Image.Image] = []
    try:
        for value in values:
            raw = base64.b64decode(value, validate=True)
            if len(raw) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="An image exceeds the 10 MB limit")
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                decoded.append(image.convert("RGB"))
        return decoded
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as exc:
        for image in decoded:
            image.close()
        raise HTTPException(status_code=422, detail="Invalid base64 image") from exc


def _set_state(value: str, error: str | None = None) -> None:
    global _state, _last_error
    with _state_lock:
        _state = value
        _last_error = error


def _begin_inference() -> None:
    global _state, _active_requests
    with _state_lock:
        if _state not in {"ready", "busy"}:
            raise ModelNotReadyError(f"Qwen embedding model is {_state}; load it first")
        _active_requests += 1
        _state = "busy"


def _end_inference() -> None:
    global _state, _active_requests
    with _state_lock:
        _active_requests = max(0, _active_requests - 1)
        if _active_requests == 0:
            _state = "ready"


def _model_status() -> ModelStatusResponse:
    with _state_lock:
        state, error = _state, _last_error
    allocated = reserved = None
    # Merely asking for status while unloaded must not initialize a CUDA
    # context, otherwise the admin page itself would retain GPU memory.
    if state in {"loading", "ready", "busy", "unloading"}:
        try:
            import torch

            if torch.cuda.is_available():
                allocated = round(torch.cuda.memory_allocated() / 1024**2, 1)
                reserved = round(torch.cuda.memory_reserved() / 1024**2, 1)
        except ImportError:
            pass
    settings = get_settings().ml
    return ModelStatusResponse(
        state=state,
        model=settings.qwen_model_name,
        dimension=2048,
        error=error,
        gpu_memory_allocated_mb=allocated,
        gpu_memory_reserved_mb=reserved,
    )


def _load_model() -> ModelStatusResponse:
    with _state_lock:
        current = _state
    if current in {"ready", "busy"}:
        return _model_status()
    if current in {"loading", "unloading"}:
        raise ModelBusyError(f"Model is currently {current}")

    _set_state("loading")
    try:
        with _inference_lock:
            get_qwen_embedding_client().load()
        _set_state("ready")
    except Exception as exc:
        _set_state("error", str(exc))
        raise
    return _model_status()


def _unload_model() -> ModelStatusResponse:
    with _state_lock:
        current, active = _state, _active_requests
    if current == "unloaded":
        return _model_status()
    if active or current in {"loading", "busy", "unloading"}:
        raise ModelBusyError(f"Model is currently {current}")

    _set_state("unloading")
    try:
        with _inference_lock:
            get_qwen_embedding_client().unload()
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
            except ImportError:
                pass
        _set_state("unloaded")
    except Exception as exc:
        _set_state("error", str(exc))
        raise
    return _model_status()


def _encode(request: EmbeddingRequest) -> list[list[float]]:
    client = get_qwen_embedding_client()
    images = _decode_images(request.images)
    begun = False
    try:
        _begin_inference()
        begun = True
        # Serializing inference prevents concurrent API and worker requests from
        # doubling peak activations on smaller GPUs.
        with _inference_lock:
            if request.mode == "text":
                return client.encode_texts(request.texts)
            if request.mode == "image":
                return client.encode_images(images)
            return client.encode_multimodal(images, request.texts)
    finally:
        for image in images:
            image.close()
        if begun:
            _end_inference()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Qwen embedding service ready; model is unloaded until requested by an admin")
    yield
    try:
        await asyncio.to_thread(_unload_model)
    except ModelBusyError:
        # Uvicorn normally drains requests before lifespan shutdown. If it is
        # force-stopped mid-inference, process exit releases CUDA memory anyway.
        logger.warning("Embedding service stopped while the model was busy")


app = FastAPI(title="Qwen Embedding Service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/model/status", response_model=ModelStatusResponse)
async def model_status(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> ModelStatusResponse:
    _authorize(authorization, x_api_key)
    return await asyncio.to_thread(_model_status)


@app.post("/model/load", response_model=ModelStatusResponse)
async def load_model(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> ModelStatusResponse:
    _authorize(authorization, x_api_key)
    try:
        return await asyncio.to_thread(_load_model)
    except ModelBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unable to load Qwen embedding model")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/model/unload", response_model=ModelStatusResponse)
async def unload_model(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> ModelStatusResponse:
    _authorize(authorization, x_api_key)
    try:
        return await asyncio.to_thread(_unload_model)
    except ModelBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unable to unload Qwen embedding model")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/embeddings", response_model=EmbeddingResponse)
async def embeddings(
    request: EmbeddingRequest,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> EmbeddingResponse:
    _authorize(authorization, x_api_key)
    try:
        vectors = await asyncio.to_thread(_encode, request)
    except ModelNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except QwenEmbeddingError as exc:
        logger.exception("Qwen embedding inference failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    dimension = len(vectors[0]) if vectors else 0
    return EmbeddingResponse(
        embeddings=vectors,
        model=get_settings().ml.qwen_model_name,
        dimension=dimension,
    )
