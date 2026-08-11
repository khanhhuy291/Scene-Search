"""Video decoding, 2FPS frame sampling, and SigLIP similarity deduplication pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image

from ml.embedder import SigLIPVisualEmbedder

logger = logging.getLogger(__name__)


def extract_and_deduplicate_frames(
    video_path: str,
    embedder: SigLIPVisualEmbedder,
    target_fps: float = 2.0,
    sim_threshold: float = 0.95
) -> List[Dict[str, Any]]:
    """Decode video at target_fps (e.g. 2FPS / 0.5s step), encode frames with SigLIP,

    and filter out near-duplicate frames where cosine similarity > sim_threshold (e.g. 0.95).

    Returns a list of dicts:
        {
            "frame_idx": int,
            "frame_no": int,
            "timestamp_sec": float,
            "image": PIL.Image,
            "siglip_vector": np.ndarray (768-dim)
        }
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    raw_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)

    # Frame step for target_fps (e.g. 30 / 2.0 = 15 frames step)
    frame_step = max(1, int(round(raw_fps / target_fps)))

    sampled_records: List[Dict[str, Any]] = []

    current_frame = 0
    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        if current_frame % frame_step == 0:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            ts_sec = round(current_frame / raw_fps, 3)

            sampled_records.append({
                "frame_idx": len(sampled_records),
                "frame_no": current_frame,
                "timestamp_sec": ts_sec,
                "image": pil_img,
            })

        current_frame += 1

    cap.release()

    if not sampled_records:
        logger.warning(f"No frames sampled from {video_path}")
        return []

    logger.info(f"Sampled {len(sampled_records)} raw 2FPS frames from {video_path} ({total_frames} total frames)")

    # 2. Encode all sampled frames with SigLIP
    pil_images = [r["image"] for r in sampled_records]
    vectors = embedder.encode_images(pil_images)

    for r, vec in zip(sampled_records, vectors):
        r["siglip_vector"] = vec

    # 3. Perform Similarity Deduplication (> 0.95 dropped)
    dedup_records: List[Dict[str, Any]] = []
    last_vec: np.ndarray | None = None

    dropped_count = 0
    for r in sampled_records:
        vec = r["siglip_vector"]
        if last_vec is None:
            dedup_records.append(r)
            last_vec = vec
        else:
            # Cosine similarity between L2-normalized vectors
            sim = float(np.dot(vec, last_vec))
            if sim > sim_threshold:
                dropped_count += 1
                continue
            else:
                dedup_records.append(r)
                last_vec = vec

    logger.info(
        f"Deduplication complete for {path.name}: "
        f"retained {len(dedup_records)} frames, dropped {dropped_count} duplicates (sim > {sim_threshold})"
    )

    return dedup_records
