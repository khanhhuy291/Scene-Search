"""Multimodal Embedding Models for SigLIP Visual and BGE-M3 Text Vectors."""

from __future__ import annotations

import logging
from typing import List, Union
import numpy as np
from PIL import Image
import torch
import open_clip
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class SigLIPVisualEmbedder:
    """SigLIP visual and text encoder producing 768-dimensional L2-normalized embeddings."""

    def __init__(
        self,
        model_name: str = "ViT-B-16-SigLIP",
        pretrained: str = "webli",
        device: str | None = None
    ) -> None:
        if device is None:
            if torch.cuda.is_available():
                try:
                    free_gb = torch.cuda.mem_get_info()[0] / (1024 ** 3)
                    device = "cuda" if free_gb >= 1.5 else "cpu"
                except Exception:
                    device = "cuda"
            else:
                device = "cpu"

        self.device = device
        logger.info(f"Loading SigLIP model '{model_name}' ({pretrained}) on device: {self.device}")
        
        try:
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                model_name, pretrained=pretrained, device=self.device
            )
        except Exception as exc:
            if self.device == "cuda":
                logger.warning(f"Failed to load SigLIP on CUDA ({exc}), falling back to CPU...")
                self.device = "cpu"
                self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                    model_name, pretrained=pretrained, device="cpu"
                )
            else:
                raise exc

        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.model.eval()

    def encode_images(self, images: List[Image.Image], batch_size: int = 32) -> np.ndarray:
        """Encode a list of PIL Images into float32 array of shape [N, 768]."""
        if not images:
            return np.zeros((0, 768), dtype=np.float32)

        all_embeddings: list[np.ndarray] = []
        for i in range(0, len(images), batch_size):
            batch_imgs = images[i : i + batch_size]
            tensors = torch.stack([self.preprocess(img) for img in batch_imgs]).to(self.device)
            with torch.no_grad():
                feats = self.model.encode_image(tensors)
                feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
            all_embeddings.append(feats.cpu().numpy().astype(np.float32))

        return np.vstack(all_embeddings)

    def encode_text(self, text: str) -> np.ndarray:
        """Encode a single text query string into float32 array of shape [1, 768]."""
        tokens = self.tokenizer([text]).to(self.device)
        with torch.no_grad():
            feats = self.model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return feats.cpu().numpy().astype(np.float32)


class BGEM3TextEmbedder:
    """BAAI/bge-m3 text embedding model producing 1024-dimensional normalized vectors."""

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str | None = None) -> None:
        if device is None:
            if torch.cuda.is_available():
                try:
                    free_gb = torch.cuda.mem_get_info()[0] / (1024 ** 3)
                    device = "cuda" if free_gb >= 1.5 else "cpu"
                except Exception:
                    device = "cuda"
            else:
                device = "cpu"

        self.device = device
        logger.info(f"Loading BGE-M3 text embedder '{model_name}' on device: {self.device}")
        
        try:
            self.model = SentenceTransformer(model_name, device=self.device)
        except Exception as exc:
            if self.device == "cuda":
                logger.warning(f"Failed to load BGE-M3 on CUDA ({exc}), falling back to CPU...")
                self.device = "cpu"
                self.model = SentenceTransformer(model_name, device="cpu")
            else:
                raise exc

    def encode_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Encode a list of text strings into float32 array of shape [N, 1024]."""
        if not texts:
            return np.zeros((0, 1024), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return np.asarray(embeddings, dtype=np.float32)
