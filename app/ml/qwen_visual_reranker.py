"""Official Qwen3-VL Native Multimodal Visual Reranker.

Evaluates relevance scores between user search queries and raw keyframe images (PIL.Image)
using Qwen3-VL-Reranker-2B via Qwen3VLForConditionalGeneration and softmax('yes', 'no') logits.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

import torch
from loguru import logger
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

from ml.device import resolve_device


class Qwen3VLVisualReranker:
    """High-performance Visual Reranker for Multimodal (Image + Text Query) scoring."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-VL-Reranker-2B",
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self._preferred_device = device
        self._processor: Any = None
        self._model: Any = None
        self._device: str = ""
        self._yes_token_id: int = 9693
        self._no_token_id: int = 2152
        self._lock = threading.Lock()

    def load(self) -> None:
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            device = resolve_device(self._preferred_device or "cuda")
            dtype = torch.float16 if device == "cuda" else torch.float32

            logger.info(
                f"Loading Qwen3-VL Visual Reranker: {self.model_name} on {device} ({dtype})..."
            )
            self._processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
            self._model = Qwen3VLForConditionalGeneration.from_pretrained(
                self.model_name,
                torch_dtype=dtype,
                trust_remote_code=True,
            ).to(device)
            self._model.eval()
            self._device = device

            # Identify yes / no token IDs
            tok = self._processor.tokenizer
            self._yes_token_id = tok("yes", add_special_tokens=False).input_ids[0]
            self._no_token_id = tok("no", add_special_tokens=False).input_ids[0]
            logger.info(
                f"Qwen3-VL Visual Reranker loaded (yes_id={self._yes_token_id}, no_id={self._no_token_id})"
            )

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, Image.Image | str]],
        batch_size: int = 8,
        show_progress_bar: bool = True,
    ) -> list[float]:
        """Compute relevance probability in [0, 1] for a sequence of (query, image_or_text) pairs."""
        if not pairs:
            return []

        self.load()
        scores: list[float] = []

        from tqdm import tqdm

        total_batches = (len(pairs) + batch_size - 1) // batch_size
        iterator = range(0, len(pairs), batch_size)
        if show_progress_bar:
            iterator = tqdm(iterator, total=total_batches, desc="Visual Rerank Batches")

        for i in iterator:
            batch = pairs[i : i + batch_size]
            prompts = []
            images = []

            for query, doc in batch:
                if isinstance(doc, Image.Image):
                    messages = [
                        {
                            "role": "system",
                            "content": "Given a search query, retrieve relevant candidates that answer the query.",
                        },
                        {"role": "query", "content": [{"type": "text", "text": query}]},
                        {"role": "document", "content": [{"type": "image", "image": doc}]},
                    ]
                    images.append(doc)
                else:
                    # Text fallback
                    messages = [
                        {
                            "role": "system",
                            "content": "Given a search query, retrieve relevant candidates that answer the query.",
                        },
                        {"role": "query", "content": [{"type": "text", "text": query}]},
                        {"role": "document", "content": [{"type": "text", "text": str(doc)}]},
                    ]

                prompt_text = self._processor.apply_chat_template(
                    messages,
                    chat_template="reranker",
                    tokenize=False,
                    add_generation_prompt=True,
                )
                prompts.append(prompt_text)

            # Build model inputs
            kwargs: dict[str, Any] = {"text": prompts, "return_tensors": "pt", "padding": True}
            if images:
                kwargs["images"] = images

            inputs = self._processor(**kwargs).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits[:, -1, :]  # last token logits
                yes_score = logits[:, self._yes_token_id]
                no_score = logits[:, self._no_token_id]
                probs = torch.softmax(torch.stack([no_score, yes_score], dim=-1), dim=-1)
                batch_scores = probs[:, 1].tolist()
                scores.extend(batch_scores)

        return scores


_visual_reranker: Qwen3VLVisualReranker | None = None
_visual_lock = threading.Lock()


def get_visual_reranker() -> Qwen3VLVisualReranker:
    global _visual_reranker
    if _visual_reranker is None:
        with _visual_lock:
            if _visual_reranker is None:
                _visual_reranker = Qwen3VLVisualReranker()
    return _visual_reranker
