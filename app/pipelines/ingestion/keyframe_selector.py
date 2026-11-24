"""Fixed, privacy-safe scene representatives in SigLIP space."""

from __future__ import annotations

import math

from ml.vectors import normalize_vectors
from pipelines.common.types import SceneRecord
from pipelines.ingestion.deduplicator import cosine


def select_representative(scene: SceneRecord) -> None:
    candidates = [
        f for f in scene.keyframes if f.privacy_status == "verified" and f.display_image is not None
    ]
    if not candidates:
        raise ValueError("Scene has no verified representative derivative")
    if any(f.embedding is None for f in candidates):
        raise ValueError("Medoid selection requires SigLIP embeddings")
    dimension = len(candidates[0].embedding)
    vectors = normalize_vectors([f.embedding for f in candidates], dimension=dimension)
    centroid = normalize_vectors(
        [
            scene.siglip_sum
            if scene.siglip_sum is not None
            else [math.fsum(v[i] for v in vectors) for i in range(dimension)]
        ],
        dimension=dimension,
    )[0]
    midpoint = (scene.start_ms + scene.end_ms) / 2
    chosen = max(
        candidates,
        key=lambda f: (
            cosine(f.embedding, centroid),
            -abs(f.timestamp_ms - midpoint),
            -f.timestamp_ms,
            -f.frame_index,
        ),
    )
    scene.representative_frame = chosen
