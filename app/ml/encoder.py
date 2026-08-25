"""SigLIP image and text encoding (ADR-0001).

The model is loaded lazily and held per process. Loading at import time would
pull torch into the API process, which never runs inference, and would load
weights once per Celery fork rather than once per worker process.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger

from core.config import MLSettings, get_settings
from ml.device import resolve_device, resolve_dtype
from ml.qwen_encoder import QwenVLEncoder

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL.Image import Image

Vector = list[float]


class EncoderError(RuntimeError):
    """Raised when the encoder cannot be loaded or run."""


class Encoder(Protocol):
    """The surface the pipeline depends on.

    Defined as a Protocol so ingestion, segmentation and search can be tested
    with a deterministic stub instead of downloading a model.
    """

    @property
    def dimension(self) -> int: ...

    @property
    def model_version(self) -> str: ...

    def encode_images(self, images: Sequence[Image]) -> list[Vector]: ...

    def encode_texts(self, texts: Sequence[str]) -> list[Vector]: ...


class SigLIPEncoder:
    """open_clip SigLIP wrapper producing L2-normalized vectors."""

    def __init__(
        self,
        settings: MLSettings | None = None,
        model_name: str = "ViT-B-16-SigLIP",
        pretrained: str = "webli",
    ) -> None:
        self.settings = settings or get_settings().ml
        if "qwen" not in self.settings.encoder_name.lower():
            self.model_name = self.settings.encoder_name
            self.pretrained = self.settings.encoder_pretrained
        else:
            self.model_name = model_name
            self.pretrained = pretrained
        self._model: Any = None
        self._preprocess: Any = None
        self._tokenizer: Any = None
        self._device: str | None = None
        self._dtype: Any = None
        self._dimension: int | None = None
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    def load(self) -> None:
        """Load weights and the tokenizer. Idempotent and thread-safe."""

        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                import open_clip
                import torch  # noqa: F401
            except ImportError as exc:
                raise EncoderError(
                    "open_clip and torch are required. Install the ML extra: make install-ml"
                ) from exc

            device = resolve_device()
            dtype = resolve_dtype(device)
            logger.info(
                "Loading {name}/{pretrained} on {device}",
                name=self.model_name,
                pretrained=self.pretrained,
                device=device,
            )
            model, _, preprocess = open_clip.create_model_and_transforms(
                self.model_name, pretrained=self.pretrained
            )
            try:
                # SigLIP tokenizes through HuggingFace transformers, which
                # open_clip declares only under its optional "training" extra.
                # Failing here, at load, is far better than failing on the first
                # search: image embedding would otherwise succeed and make
                # ingestion look healthy while query encoding was impossible.
                tokenizer = open_clip.get_tokenizer(self.model_name)
            except ImportError as exc:
                raise EncoderError(
                    f"{self.model_name} needs a HuggingFace tokenizer, which "
                    "requires transformers and sentencepiece. Install the ML extra: "
                    "make install-ml"
                ) from exc

            self._model = model.to(device=device, dtype=dtype).eval()
            self._preprocess = preprocess
            self._tokenizer = tokenizer
            self._device = device
            self._dtype = dtype

    def unload(self) -> None:
        self._model = self._preprocess = self._tokenizer = None
        self._dimension = None

    # -- properties --------------------------------------------------------

    @property
    def model_version(self) -> str:
        return f"{self.model_name}/{self.pretrained}"

    @property
    def device(self) -> str:
        self.load()
        assert self._device is not None
        return self._device

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.encode_texts([""])[0])
        return self._dimension

    # -- encoding ----------------------------------------------------------

    def _normalize(self, features: Any) -> list[Vector]:
        features = features / features.norm(dim=-1, keepdim=True)
        return [[float(value) for value in row] for row in features.float().cpu()]

    def encode_images(self, images: Sequence[Image]) -> list[Vector]:
        """Embed images in configured batches, returning normalized vectors."""

        if not images:
            return []
        self.load()
        import torch

        vectors: list[Vector] = []
        batch_size = self.settings.batch_size
        with torch.inference_mode():
            for start in range(0, len(images), batch_size):
                chunk = images[start : start + batch_size]
                tensor = torch.stack([self._preprocess(image) for image in chunk]).to(
                    device=self._device, dtype=self._dtype
                )
                vectors.extend(self._normalize(self._model.encode_image(tensor)))
        return vectors

    def encode_texts(self, texts: Sequence[str]) -> list[Vector]:
        """Embed query strings into the same space as the image tower."""

        if not texts:
            return []
        self.load()
        import torch

        with torch.inference_mode():
            tokens = self._tokenizer(list(texts)).to(self._device)
            return self._normalize(self._model.encode_text(tokens))


_encoder: Encoder | None = None
_qwen_encoder: Encoder | None = None
_siglip_encoder: Encoder | None = None
# ``get_encoder`` delegates to one of the specialised getters while holding
# this lock, and those getters acquire the same lock to initialise their own
# singleton.  A regular Lock deadlocks the worker before the ingestion pipeline
# can report its first progress update.  RLock preserves singleton
# serialisation while allowing that intentional nested acquisition.
_encoder_lock = threading.RLock()


def get_qwen_encoder() -> Encoder:
    global _qwen_encoder
    if _qwen_encoder is None:
        with _encoder_lock:
            if _qwen_encoder is None:
                _qwen_encoder = QwenVLEncoder()
    return _qwen_encoder


def get_siglip_encoder() -> Encoder:
    global _siglip_encoder
    if _siglip_encoder is None:
        with _encoder_lock:
            if _siglip_encoder is None:
                _siglip_encoder = SigLIPEncoder()
    return _siglip_encoder


def get_encoder() -> Encoder:
    """Return the process-wide encoder, constructing it lazily.

    Construction does not load weights; the first ``encode_*`` call does. This
    keeps Celery startup responsive and makes model loading part of the visible
    embedding stage instead of blocking worker initialization.
    """

    global _encoder
    if _encoder is None:
        with _encoder_lock:
            if _encoder is None:
                settings = get_settings().ml
                if "qwen" in settings.encoder_name.lower():
                    _encoder = get_qwen_encoder()
                else:
                    _encoder = get_siglip_encoder()
    return _encoder


def warm_encoder() -> None:
    """Eagerly load weights in the current process."""

    encoder = get_encoder()
    if hasattr(encoder, "load"):
        encoder.load()


def reset_encoder() -> None:
    """Drop the cached encoder (used by tests)."""

    global _encoder, _qwen_encoder, _siglip_encoder
    if _encoder is not None and hasattr(_encoder, "unload"):
        _encoder.unload()
    _encoder = None
    _qwen_encoder = None
    _siglip_encoder = None


def batched(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


__all__ = [
    "Encoder",
    "EncoderError",
    "QwenVLEncoder",
    "SigLIPEncoder",
    "Vector",
    "batched",
    "get_encoder",
    "get_qwen_encoder",
    "get_siglip_encoder",
    "reset_encoder",
    "warm_encoder",
]
