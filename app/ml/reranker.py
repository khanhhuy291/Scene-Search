"""Cross-encoder reranking module using Qwen3-VL-Reranker-2B or text cross-encoders.

Performs fine-grained cross-attention relevance scoring over candidate keyframes
retrieved in the first stage (ANN / hybrid retrieval).
"""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from loguru import logger

from core.config import get_settings
from ml.device import resolve_device, resolve_dtype


class RerankerError(RuntimeError):
    """Raised when reranking fails."""


class QwenVLReranker:
    """Multimodal / text CrossEncoder wrapper for stage-2 candidate reranking."""

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name or "Qwen/Qwen3-VL-Reranker-2B"
        self._preferred_device = device
        self._model: Any = None
        self._device: str = ""
        self._lock = threading.Lock()

    def load(self) -> None:
        """Lazily load the cross-encoder model."""
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            settings = get_settings().search
            target_model = (
                self.model_name or settings.reranker_model_name or "Qwen/Qwen3-VL-Reranker-2B"
            )
            pref = self._preferred_device or settings.reranker_device
            device = resolve_device(pref if pref != "auto" else None)
            dtype = resolve_dtype(device)
            logger.info(
                "Loading Reranker model {model_name} on {device}",
                model_name=target_model,
                device=device,
            )

            try:
                import torch
                from sentence_transformers import CrossEncoder

                model_kwargs = {}
                if device == "cuda":
                    model_kwargs["torch_dtype"] = torch.float16 if dtype == torch.float32 else dtype

                self._model = CrossEncoder(
                    target_model,
                    device=device,
                    model_kwargs=model_kwargs,
                    trust_remote_code=True,
                )
                self._device = device
                logger.info(
                    "Reranker model {model_name} loaded successfully", model_name=target_model
                )
            except Exception as exc:
                logger.exception(
                    "Failed to load reranker {model_name}: {exc}", model_name=target_model, exc=exc
                )
                raise RerankerError(f"Failed to load reranker {target_model}: {exc}") from exc

    def _build_doc_text(self, keyframe: Any) -> str:
        """Construct comprehensive contextual text representation of a keyframe."""
        parts = []
        if getattr(keyframe, "caption", None):
            parts.append(keyframe.caption)

        ctx_parts = []
        if getattr(keyframe, "scene_type", None):
            ctx_parts.append(f"Scene: {keyframe.scene_type}")
        if getattr(keyframe, "time_of_day", None):
            ctx_parts.append(f"Time: {keyframe.time_of_day}")
        if getattr(keyframe, "weather", None):
            ctx_parts.append(f"Weather: {keyframe.weather}")
        if getattr(keyframe, "retrieval_tags", None):
            ctx_parts.append(f"Tags: {', '.join(keyframe.retrieval_tags)}")

        if ctx_parts:
            parts.append(f"[{' | '.join(ctx_parts)}]")

        return " ".join(parts) if parts else "Keyframe scene"

    def rerank(
        self,
        query: str,
        candidates: Sequence[Any],
        *,
        top_k: int | None = None,
        mode: str | None = None,
    ) -> list[Any]:
        """Rerank candidate matches against query using text metadata or visual image tokens."""
        if not candidates:
            return []

        try:
            self.load()
            assert self._model is not None
        except Exception as exc:
            logger.warning("Reranker unavailable, keeping original ranking: {}", exc)
            return list(candidates[:top_k] if top_k else candidates)

        try:
            settings = get_settings().search
            limit = min(len(candidates), top_k) if top_k else len(candidates)
            pool_size = max(limit, settings.rerank_top_k)
            to_score = list(candidates[:pool_size])
            documents = [self._build_doc_text(c.keyframe) for c in to_score]

            target_mode = mode or getattr(settings, "rerank_mode", "text")

            # 1. Visual Multimodal Reranking (uses Redis Image Cache)
            if target_mode == "visual":
                try:
                    import asyncio

                    from ml.image_cache import get_image_cache

                    items_to_fetch = [
                        (
                            getattr(c.keyframe, "video_id", ""),
                            getattr(c.keyframe, "frame_name", "")
                            or getattr(c.keyframe, "name", ""),
                        )
                        for c in to_score
                    ]
                    # Fetch batch images from Redis (sync wrapper if running synchronously)
                    cache = get_image_cache()
                    try:
                        asyncio.get_running_loop()
                        # If inside active event loop
                        import concurrent.futures

                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(
                                asyncio.run, cache.get_images_batch(items_to_fetch)
                            )
                            images = future.result()
                    except RuntimeError:
                        images = asyncio.run(cache.get_images_batch(items_to_fetch))

                    pairs = [
                        (query, img if img is not None else doc)
                        for img, doc in zip(images, documents)
                    ]
                    scores = self._model.predict(pairs)
                    rankings = [
                        {"corpus_id": idx, "score": float(sc)} for idx, sc in enumerate(scores)
                    ]
                    rankings.sort(key=lambda x: x["score"], reverse=True)
                    rankings = rankings[:limit]
                except Exception as exc:
                    logger.warning("Visual reranking fallback to text: {}", exc)
                    rankings = self._model.rank(query, documents, top_k=limit)
            else:
                # 2. Text Metadata Reranking (Default fast mode)
                rankings = self._model.rank(query, documents, top_k=limit)

            reranked = []
            for rank_item in rankings:
                idx = rank_item["corpus_id"]
                raw_score = float(rank_item["score"])
                # Normalize raw cross-encoder logit to [0, 1] via stable sigmoid
                if raw_score >= 0:
                    score = 1.0 / (1.0 + math.exp(-raw_score))
                else:
                    z = math.exp(raw_score)
                    score = z / (1.0 + z)
                score = round(score, 6)

                match = to_score[idx]
                signals = dict(match.signals)
                signals["rerank"] = score
                updated_match = replace(match, score=score, signals=signals)
                reranked.append(updated_match)

            return reranked
        except Exception as exc:
            logger.warning("Reranking execution failed, keeping original order: {}", exc)
            return list(candidates[:top_k] if top_k else candidates)


_reranker: QwenVLReranker | None = None
_reranker_lock = threading.Lock()


def get_reranker() -> QwenVLReranker:
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                _reranker = QwenVLReranker()
    return _reranker


def reset_reranker() -> None:
    global _reranker
    with _reranker_lock:
        _reranker = None


__all__ = [
    "QwenVLReranker",
    "RerankerError",
    "get_reranker",
    "reset_reranker",
]
