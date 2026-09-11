"""Qwen/Qwen3-VL-Embedding-2B ML embedding client and encoder implementation.

Provides multimodal embedding generation (images, text, image-text pairs, and
scene summaries) for ingestion and summarization pipelines.
"""

from __future__ import annotations

import base64
import io
import threading
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from loguru import logger

from core.config import MLSettings, get_settings
from ml.device import resolve_device, resolve_dtype

if TYPE_CHECKING:  # pragma: no cover
    from PIL.Image import Image

Vector = list[float]


class QwenEmbeddingError(RuntimeError):
    """Raised when the Qwen3-VL embedding generation fails."""


class QwenVLEmbeddingClient:
    """ML client for Qwen/Qwen3-VL-Embedding-2B.

    Generates L2-normalized multimodal embeddings for images, text queries,
    scene summaries, and image-text pairs using SentenceTransformer, local Transformers,
    or a remote inference endpoint.
    """

    DEFAULT_DIMENSION: int = 2048

    def __init__(self, settings: MLSettings | None = None) -> None:
        self.settings = settings or get_settings().ml
        self._model: Any = None
        self._st_model: Any = None
        self._processor: Any = None
        self._device: str | None = None
        self._dtype: Any = None
        self._dimension: int = self.DEFAULT_DIMENSION
        self._lock = threading.Lock()

    # -- Lifecycle ---------------------------------------------------------

    def load(self) -> None:
        """Lazily load weights if running locally. Idempotent and thread-safe."""

        has_local = self._model is not None or self._st_model is not None
        if has_local or self.settings.qwen_embedding_url:
            return

        with self._lock:
            has_local = self._st_model is not None or self._model is not None
            if has_local or self.settings.qwen_embedding_url:
                return

            model_name = self.settings.qwen_model_name or "Qwen/Qwen3-VL-Embedding-2B"

            try:
                device = resolve_device()
                dtype = resolve_dtype(device)
                logger.info(
                    "Loading Qwen embedding model {model_name} on {device}",
                    model_name=model_name,
                    device=device,
                )
                import torch
                from sentence_transformers import SentenceTransformer

                model_kwargs = {}
                if device == "cuda":
                    model_kwargs["torch_dtype"] = torch.float16 if dtype == torch.float32 else dtype

                st_model = SentenceTransformer(
                    model_name,
                    device=device,
                    model_kwargs=model_kwargs,
                    local_files_only=False,
                )
                self._st_model = st_model
                self._device = device

                dim = getattr(st_model, "get_sentence_embedding_dimension", lambda: None)()
                if dim:
                    self._dimension = dim
            except Exception as exc:
                logger.exception(
                    "Failed to load Qwen embedding model {model_name}: {exc}",
                    model_name=model_name,
                    exc=exc,
                )
                raise QwenEmbeddingError(
                    f"Failed to load Qwen embedding model {model_name}: {exc}"
                ) from exc

    def unload(self) -> None:
        """Unload local model and processor."""

        with self._lock:
            self._model = None
            self._st_model = None
            self._processor = None

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_version(self) -> str:
        return "qwen3-vl-embedding-2b-v1"

    # -- Helpers -----------------------------------------------------------

    def _normalize(self, vectors: Any) -> list[Vector]:
        """L2-normalize torch tensor or list of float lists."""
        try:
            import torch
        except ImportError:
            torch = None

        if torch is not None and isinstance(vectors, torch.Tensor):
            normed = vectors / vectors.norm(dim=-1, keepdim=True).clamp(min=1e-12)
            return [[float(v) for v in row] for row in normed.float().cpu()]

        result: list[Vector] = []
        for vec in vectors:
            sq_sum = sum(x * x for x in vec)
            norm = (sq_sum**0.5) if sq_sum > 0 else 1.0
            result.append([x / norm for x in vec])
        return result

    def _image_to_base64(self, image: Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _prepare_images(self, images: Sequence[Image]) -> tuple[list[Image], list[Image]]:
        """Bound image size before local inference or HTTP serialization."""
        from PIL import Image as PILImage

        prepared: list[Image] = []
        owned: list[Image] = []
        for image in images:
            if max(image.size) > self.settings.image_size:
                copy = image.copy()
                copy.thumbnail(
                    (self.settings.image_size, self.settings.image_size),
                    PILImage.Resampling.LANCZOS,
                )
                prepared.append(copy)
                owned.append(copy)
            else:
                prepared.append(image)
        return prepared, owned

    def _encode_remote(
        self,
        *,
        images: Sequence[Image] | None = None,
        texts: Sequence[str] | None = None,
        mode: str = "multimodal",
    ) -> list[Vector]:
        """Fallback to HTTP endpoint if qwen_embedding_url is set."""
        import httpx

        url = self.settings.qwen_embedding_url
        if not url:
            raise QwenEmbeddingError("qwen_embedding_url is not configured")

        headers: dict[str, str] = {}
        if self.settings.qwen_embedding_api_key:
            headers["Authorization"] = (
                f"Bearer {self.settings.qwen_embedding_api_key.get_secret_value()}"
            )

        raw_bs = getattr(self.settings, "batch_size", 16)
        batch_size = max(1, min(raw_bs if isinstance(raw_bs, int) else 16, 32))
        vectors: list[Vector] = []

        try:
            with httpx.Client(timeout=self.settings.qwen_embedding_timeout) as client:

                def _post_with_retry(payload: dict[str, Any]) -> dict[str, Any]:
                    import time

                    retries = 4
                    delay = 1.0
                    for attempt in range(retries):
                        try:
                            resp = client.post(
                                f"{url.rstrip('/')}/embeddings", json=payload, headers=headers
                            )
                            if resp.status_code == 503 and attempt < retries - 1:
                                time.sleep(delay)
                                delay = min(delay * 1.5, 4.0)
                                continue
                            resp.raise_for_status()
                            return resp.json()
                        except httpx.ConnectError:
                            if attempt < retries - 1:
                                time.sleep(delay)
                                delay = min(delay * 1.5, 4.0)
                                continue
                            raise
                    resp = client.post(
                        f"{url.rstrip('/')}/embeddings", json=payload, headers=headers
                    )
                    resp.raise_for_status()
                    return resp.json()

                if mode == "multimodal" and images and texts:
                    for start in range(0, len(images), batch_size):
                        chunk_imgs = images[start : start + batch_size]
                        chunk_txts = texts[start : start + batch_size]
                        payload = {
                            "model": "qwen",
                            "mode": "multimodal",
                            "images": [self._image_to_base64(img) for img in chunk_imgs],
                            "texts": list(chunk_txts),
                        }
                        data = _post_with_retry(payload)
                        vectors.extend(data.get("embeddings", []))
                elif texts:
                    for start in range(0, len(texts), batch_size):
                        chunk_txts = texts[start : start + batch_size]
                        payload = {
                            "model": "qwen",
                            "mode": "text",
                            "texts": list(chunk_txts),
                        }
                        data = _post_with_retry(payload)
                        vectors.extend(data.get("embeddings", []))
                elif images:
                    for start in range(0, len(images), batch_size):
                        chunk_imgs = images[start : start + batch_size]
                        payload = {
                            "model": "qwen",
                            "mode": "image",
                            "images": [self._image_to_base64(img) for img in chunk_imgs],
                        }
                        data = _post_with_retry(payload)
                        vectors.extend(data.get("embeddings", []))

                expected = len(texts or images or [])
                if len(vectors) != expected:
                    raise QwenEmbeddingError(
                        f"Remote endpoint returned {len(vectors)} embeddings for {expected} inputs"
                    )
                if vectors and len(vectors[0]) != self.DEFAULT_DIMENSION:
                    raise QwenEmbeddingError(
                        f"Remote endpoint returned dimension {len(vectors[0])}; "
                        f"expected {self.DEFAULT_DIMENSION}"
                    )
                return self._normalize(vectors)
        except httpx.HTTPStatusError as exc:
            raise QwenEmbeddingError(
                f"Remote Qwen embedding HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except Exception as exc:
            raise QwenEmbeddingError(f"Remote Qwen embedding request failed: {exc}") from exc

    # -- Core Encoding Methods ----------------------------------------------

    def _encode_local_images(self, images: Sequence[Image], batch_size: int) -> Any:
        """Encode images, reducing the CUDA batch automatically after an OOM."""
        assert self._st_model is not None
        try:
            return self._st_model.encode(
                list(images),
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            try:
                import torch
            except ImportError:
                raise
            if not isinstance(exc, torch.OutOfMemoryError) or batch_size <= 1:
                raise
            torch.cuda.empty_cache()
            reduced = max(1, batch_size // 2)
            logger.warning(
                "CUDA OOM while embedding {count} images at batch {batch}; retrying at {reduced}",
                count=len(images),
                batch=batch_size,
                reduced=reduced,
            )
            outputs: list[Vector] = []
            for start in range(0, len(images), reduced):
                encoded = self._encode_local_images(images[start : start + reduced], reduced)
                outputs.extend(encoded.tolist() if hasattr(encoded, "tolist") else encoded)
            return outputs

    def encode_images(self, images: Sequence[Image]) -> list[Vector]:
        """Generate embeddings for a sequence of PIL images."""

        if not images:
            return []

        # Qwen uses dynamic image tokenization. Bounding the longest edge keeps
        # activation and HTTP payload memory predictable; source frames are not
        # mutated because the pipeline still owns them.
        prepared, owned = self._prepare_images(images)
        try:
            if self._st_model is None and self.settings.qwen_embedding_url:
                return self._encode_remote(images=prepared, mode="image")

            self.load()
            if self._st_model is None:
                raise QwenEmbeddingError("SentenceTransformer model for Qwen is not loaded")
            embeddings = self._encode_local_images(
                prepared, min(len(prepared), self.settings.batch_size)
            )
            if hasattr(embeddings, "tolist"):
                return embeddings.tolist()
            return [list(v) for v in embeddings]
        finally:
            for image in owned:
                image.close()

    def encode_texts(self, texts: Sequence[str]) -> list[Vector]:
        """Generate embeddings for a sequence of text strings or queries."""

        if not texts:
            return []

        if self._st_model is None and self.settings.qwen_embedding_url:
            return self._encode_remote(texts=texts, mode="text")

        self.load()

        if self._st_model is None:
            raise QwenEmbeddingError("SentenceTransformer model for Qwen is not loaded")

        embeddings = self._st_model.encode(
            list(texts),
            batch_size=min(len(texts), self.settings.batch_size),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()
        return [list(v) for v in embeddings]

    def encode_multimodal(self, images: Sequence[Image], texts: Sequence[str]) -> list[Vector]:
        """Generate joint embeddings for paired image and text inputs."""

        if len(images) != len(texts):
            raise ValueError("Number of images must match number of text prompts")
        if not images:
            return []

        if self._st_model is None and self.settings.qwen_embedding_url:
            prepared, owned = self._prepare_images(images)
            try:
                return self._encode_remote(images=prepared, texts=texts, mode="multimodal")
            finally:
                for image in owned:
                    image.close()

        self.load()

        if self._st_model is None:
            raise QwenEmbeddingError("SentenceTransformer model for Qwen is not loaded")

        inputs = [f"{t}" for t in texts]
        embeddings = self._st_model.encode(
            inputs,
            batch_size=min(len(images), self.settings.batch_size),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()
        return [list(v) for v in embeddings]

    def encode_summary(
        self,
        summary_texts: Sequence[str],
        images: Sequence[Image] | None = None,
    ) -> list[Vector]:
        """Generate scene summary embeddings from text summaries and optional keyframe images."""

        if images and len(images) == len(summary_texts):
            return self.encode_multimodal(images=images, texts=summary_texts)
        return self.encode_texts(summary_texts)


_qwen_client: QwenVLEmbeddingClient | None = None
_qwen_client_lock = threading.Lock()


def get_qwen_embedding_client() -> QwenVLEmbeddingClient:
    """Return process-wide QwenVLEmbeddingClient, initializing lazily."""
    global _qwen_client
    if _qwen_client is None:
        with _qwen_client_lock:
            if _qwen_client is None:
                _qwen_client = QwenVLEmbeddingClient()
    return _qwen_client


def reset_qwen_embedding_client() -> None:
    """Reset cached Qwen embedding client (used for testing)."""
    global _qwen_client
    if _qwen_client is not None:
        _qwen_client.unload()
    _qwen_client = None


class QwenVLEncoder:
    """Encoder adapter implementing the Encoder protocol using QwenVLEmbeddingClient."""

    def __init__(
        self,
        settings: MLSettings | None = None,
        client: QwenVLEmbeddingClient | None = None,
    ) -> None:
        self.settings = settings or get_settings().ml
        self._client = client

    @property
    def client(self) -> QwenVLEmbeddingClient:
        if self._client is None:
            self._client = get_qwen_embedding_client()
        return self._client

    def load(self) -> None:
        """Eagerly load model weights."""
        self.client.load()

    def unload(self) -> None:
        """Unload model weights."""
        if self._client:
            self._client.unload()

    @property
    def model_version(self) -> str:
        if "qwen" in self.settings.encoder_name.lower():
            return "qwen3-vl-embedding-2b-v1"
        return getattr(self.client, "model_version", "qwen3-vl-embedding-2b-v1")

    @property
    def dimension(self) -> int:
        return self.client.dimension

    def encode_images(self, images: Sequence[Image]) -> list[Vector]:
        return self.client.encode_images(images)

    def encode_texts(self, texts: Sequence[str]) -> list[Vector]:
        return self.client.encode_texts(texts)

    def encode_multimodal(self, images: Sequence[Image], texts: Sequence[str]) -> list[Vector]:
        return self.client.encode_multimodal(images, texts)

    def encode_summary(
        self,
        summary_texts: Sequence[str],
        images: Sequence[Image] | None = None,
    ) -> list[Vector]:
        return self.client.encode_summary(summary_texts, images)


__all__ = [
    "QwenEmbeddingError",
    "QwenVLEmbeddingClient",
    "QwenVLEncoder",
    "Vector",
    "get_qwen_embedding_client",
    "reset_qwen_embedding_client",
]
