"""Hybrid Search Engine combining SigLIP visual vectors and BGE-M3 text vectors in Qdrant via RRF."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np

from infrastructure.qdrant import get_qdrant_client
from ml.embedder import SigLIPVisualEmbedder, BGEM3TextEmbedder

logger = logging.getLogger(__name__)


class HybridQdrantSearchEngine:
    """Hybrid Retriever for Qdrant named vectors 'siglip_visual' and 'bge_text'."""

    def __init__(
        self,
        collection_name: str = "scenes",
        siglip_embedder: Optional[SigLIPVisualEmbedder] = None,
        bge_embedder: Optional[BGEM3TextEmbedder] = None,
    ) -> None:
        self.collection_name = collection_name
        self.siglip_embedder = siglip_embedder or SigLIPVisualEmbedder()
        self.bge_embedder = bge_embedder or BGEM3TextEmbedder()
        self.qdrant = get_qdrant_client()

    async def search(
        self,
        query_text: str,
        top_k: int = 10,
        alpha_visual: float = 0.5,
        alpha_text: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Perform Hybrid Search in Qdrant fusing SigLIP visual query vector + BGE-M3 text query vector."""
        if not query_text or not query_text.strip():
            return []

        query = query_text.strip()
        fetch_k = max(top_k * 3, 30)

        # 1. Encode query text with SigLIP (768d) and BGE-M3 (1024d)
        siglip_vec = self.siglip_embedder.encode_text(query)[0].tolist()
        bge_vec = self.bge_embedder.encode_texts([query])[0].tolist()

        # 2. Query Qdrant for visual similarity
        visual_res = (
            await self.qdrant.query_points(
                collection_name=self.collection_name,
                query=siglip_vec,
                using="siglip_visual",
                limit=fetch_k,
                with_payload=True,
            )
        ).points

        # 3. Query Qdrant for text similarity
        text_res = (
            await self.qdrant.query_points(
                collection_name=self.collection_name,
                query=bge_vec,
                using="bge_text",
                limit=fetch_k,
                with_payload=True,
            )
        ).points

        # 4. RRF (Reciprocal Rank Fusion)
        k_rrf = 60.0
        scores: Dict[str, float] = {}
        payloads: Dict[str, Dict[str, Any]] = {}
        v_scores: Dict[str, float] = {}
        t_scores: Dict[str, float] = {}

        for rank, item in enumerate(visual_res, 1):
            pid = str(item.id)
            scores[pid] = scores.get(pid, 0.0) + alpha_visual * (1.0 / (k_rrf + rank))
            payloads[pid] = item.payload or {}
            v_scores[pid] = float(item.score)

        for rank, item in enumerate(text_res, 1):
            pid = str(item.id)
            scores[pid] = scores.get(pid, 0.0) + alpha_text * (1.0 / (k_rrf + rank))
            if pid not in payloads:
                payloads[pid] = item.payload or {}
            t_scores[pid] = float(item.score)

        # Sort by final RRF score
        sorted_pids = sorted(scores.keys(), key=lambda pid: scores[pid], reverse=True)

        results: List[Dict[str, Any]] = []
        for pid in sorted_pids[:top_k]:
            pl = payloads[pid]
            results.append({
                "id": pid,
                "score": float(scores[pid] * 100.0),
                "visual_score": v_scores.get(pid, 0.0),
                "text_score": t_scores.get(pid, 0.0),
                "video_id": pl.get("video_id", ""),
                "video_path": pl.get("video_path", ""),
                "timestamp_sec": pl.get("timestamp_sec", 0.0),
                "frame_no": pl.get("frame_no", -1),
                "qwen_caption": pl.get("qwen_caption", ""),
            })

        return results
