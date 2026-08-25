"""Inference device resolution (ADR-0001).

Kept free of torch imports at module scope so that the API process, which never
runs inference, does not pay torch's import cost or require the ``[ml]`` extra.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.config import get_settings


def resolve_device(preference: str | None = None) -> str:
    """Return the torch device string to use for inference.

    ``auto`` prefers MPS, then CUDA, then CPU. On an Apple silicon host this
    resolves to ``mps`` only when the process runs natively: Docker Desktop on
    macOS cannot pass the Metal device through to a container, so a containerized
    worker silently lands on CPU and runs roughly ten times slower. That is why
    the worker is run with ``make worker`` on the host rather than in Compose.
    """

    settings = get_settings().ml
    choice = (preference or settings.device).lower()

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - depends on the [ml] extra
        raise RuntimeError(
            "PyTorch is not installed. Install the ML extra: pip install -e '.[ml,dev]'"
        ) from exc

    if choice == "auto":
        if torch.backends.mps.is_available():
            resolved = "mps"
        elif torch.cuda.is_available():
            resolved = "cuda"
        else:
            resolved = "cpu"
        logger.info("Resolved inference device to {device}", device=resolved)
        return resolved

    if choice == "mps" and not torch.backends.mps.is_available():
        logger.warning("MPS was requested but is unavailable; falling back to CPU")
        return "cpu"
    if choice == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA was requested but is unavailable; falling back to CPU")
        return "cpu"
    return choice


def resolve_dtype(device: str) -> Any:
    """Return the torch dtype for the resolved device.

    Half precision is refused on MPS regardless of configuration: several
    transformer operators have produced numerical anomalies there, and at this
    corpus size fp32 is fast enough that the risk buys nothing.
    """

    import torch

    settings = get_settings().ml
    if settings.dtype == "float16":
        if device == "mps":
            logger.warning("float16 is not used on MPS; falling back to float32")
            return torch.float32
        return torch.float16
    return torch.float32


__all__ = ["resolve_device", "resolve_dtype"]
