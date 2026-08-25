"""Evaluation script for Qwen Embedding models and Qwen Reranker on Golden Set (eval.csv).

Measures HitRate@K (Hit@1, Hit@3, Hit@5, Hit@10, Hit@20, Hit@50) and Mean Reciprocal Rank (MRR)
at both Frame-level (exact matching frame) and Video-level (matching parent video).
Supports side-by-side comparison of Before vs After Rerank, and Base vs Fine-tuned Checkpoints.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure .env is loaded regardless of current working directory
for env_path in [
    Path.cwd() / ".env",
    Path.cwd() / "app" / ".env",
    Path(__file__).resolve().parents[1] / ".env",
]:
    if env_path.exists():
        load_dotenv(env_path)

from loguru import logger

from core.config import get_settings
from infrastructure.qdrant import get_qdrant_client
from ml.device import resolve_device, resolve_dtype


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    header_str = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    divider_str = "|-" + "-|-".join("-" * widths[i] for i in range(len(headers))) + "-|"
    row_strs = [
        "| " + " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_str, divider_str, *row_strs])


@dataclass
class QueryResult:
    query_id: str
    caption: str
    gt_video_id: str
    gt_frame_id: int
    gt_frame_name: str
    video_rank: int | None = None
    frame_rank: int | None = None  # Exact frame match
    tolerant_frame_rank: int | None = None  # Match within tolerance_frames window
    top1_video_id: str = ""
    top1_frame_id: Any = None
    top1_frame_name: str = ""
    top1_score: float = 0.0


@dataclass
class EvaluationReport:
    model_name: str
    total_queries: int
    duration_s: float
    tolerance_frames: int = 4
    # Frame-Level Metrics (Exact Frame)
    frame_hit1: float = 0.0
    frame_hit3: float = 0.0
    frame_hit5: float = 0.0
    frame_hit10: float = 0.0
    frame_hit20: float = 0.0
    frame_hit50: float = 0.0
    frame_mrr5: float = 0.0
    frame_mrr10: float = 0.0
    frame_mrr20: float = 0.0
    frame_mrr50: float = 0.0
    frame_mrr: float = 0.0
    # Tolerant / Relaxed Frame-Level Metrics (Within tolerance_frames)
    tol_frame_hit1: float = 0.0
    tol_frame_hit3: float = 0.0
    tol_frame_hit5: float = 0.0
    tol_frame_hit10: float = 0.0
    tol_frame_hit20: float = 0.0
    tol_frame_hit50: float = 0.0
    tol_frame_mrr5: float = 0.0
    tol_frame_mrr10: float = 0.0
    tol_frame_mrr20: float = 0.0
    tol_frame_mrr50: float = 0.0
    tol_frame_mrr: float = 0.0
    # Video-Level Metrics (Correct Video)
    video_hit1: float = 0.0
    video_hit3: float = 0.0
    video_hit5: float = 0.0
    video_hit10: float = 0.0
    video_hit20: float = 0.0
    video_hit50: float = 0.0
    video_mrr5: float = 0.0
    video_mrr10: float = 0.0
    video_mrr20: float = 0.0
    video_mrr50: float = 0.0
    video_mrr: float = 0.0
    query_results: list[QueryResult] = field(default_factory=list)


def load_ground_truth(csv_path: str | Path) -> list[dict[str, Any]]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Evaluation CSV not found at: {path.resolve()}")

    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                fid = int(r["frame_id"])
            except Exception:
                fid = r["frame_id"]
            rows.append(
                {
                    "query_id": str(r.get("query_id", "")),
                    "caption": str(r.get("caption", "")).strip(),
                    "video_id": str(r.get("video_id", "")).strip(),
                    "frame_id": fid,
                    "frame_name": str(r.get("frame_name", "")).strip(),
                    "gt_path": str(r.get("gt_path", "")).strip(),
                }
            )
    return rows


def load_sentence_transformer(model_name_or_path: str, device: str) -> Any:
    import torch
    from sentence_transformers import SentenceTransformer

    dtype = resolve_dtype(device)
    model_kwargs = {}
    if device == "cuda":
        model_kwargs["torch_dtype"] = torch.float16 if dtype == torch.float32 else dtype

    logger.info(f"Loading embedding model: {model_name_or_path} on {device}...")
    model = SentenceTransformer(
        model_name_or_path,
        device=device,
        model_kwargs=model_kwargs,
        trust_remote_code=True,
    )
    return model


def load_cross_encoder(model_name_or_path: str, device: str) -> Any:
    import torch
    from sentence_transformers import CrossEncoder

    model_kwargs = {}
    if device == "cuda":
        model_kwargs["torch_dtype"] = torch.float16

    logger.info(f"Loading CrossEncoder reranker: {model_name_or_path} on {device}...")
    model = CrossEncoder(
        model_name_or_path,
        device=device,
        model_kwargs=model_kwargs,
        trust_remote_code=True,
    )
    return model


def build_candidate_text(payload: dict[str, Any]) -> str:
    parts = []
    caption = payload.get("caption") or (payload.get("metadata", {}).get("caption"))
    if caption:
        parts.append(str(caption))

    meta = payload.get("metadata", {})
    scene_info = meta.get("scene", {})
    ctx = []
    scene_type = (
        payload.get("scene_type") or scene_info.get("scene_type") or scene_info.get("road_type")
    )
    if scene_type and scene_type != "unknown":
        ctx.append(f"Scene: {scene_type}")
    time_of_day = payload.get("time_of_day") or scene_info.get("time_of_day")
    if time_of_day and time_of_day != "unknown":
        ctx.append(f"Time: {time_of_day}")
    weather = payload.get("weather") or scene_info.get("weather")
    if weather and weather != "unknown":
        ctx.append(f"Weather: {weather}")
    tags = payload.get("retrieval_tags") or meta.get("retrieval_tags") or []
    if tags:
        ctx.append("Tags: " + ", ".join(tags[:5]))

    if ctx:
        parts.append("[" + " | ".join(ctx) + "]")

    return " ".join(parts) if parts else "Keyframe scene"


def compute_metrics(
    query_results: list[QueryResult],
    total: int,
    model_name: str,
    duration_s: float,
    tolerance_frames: int = 4,
) -> EvaluationReport:
    def calc_hit(ranks: list[int | None], k: int) -> float:
        hits = sum(1 for r in ranks if r is not None and r <= k)
        return hits / total if total > 0 else 0.0

    def calc_mrr(ranks: list[int | None], k: int | None = None) -> float:
        reciprocal_sum = 0.0
        for r in ranks:
            if r is not None and (k is None or r <= k):
                reciprocal_sum += 1.0 / r
        return reciprocal_sum / total if total > 0 else 0.0

    v_ranks = [qr.video_rank for qr in query_results]
    f_ranks = [qr.frame_rank for qr in query_results]
    tf_ranks = [qr.tolerant_frame_rank for qr in query_results]

    return EvaluationReport(
        model_name=model_name,
        total_queries=total,
        duration_s=duration_s,
        tolerance_frames=tolerance_frames,
        # Exact Frame-Level
        frame_hit1=calc_hit(f_ranks, 1),
        frame_hit3=calc_hit(f_ranks, 3),
        frame_hit5=calc_hit(f_ranks, 5),
        frame_hit10=calc_hit(f_ranks, 10),
        frame_hit20=calc_hit(f_ranks, 20),
        frame_hit50=calc_hit(f_ranks, 50),
        frame_mrr5=calc_mrr(f_ranks, 5),
        frame_mrr10=calc_mrr(f_ranks, 10),
        frame_mrr20=calc_mrr(f_ranks, 20),
        frame_mrr50=calc_mrr(f_ranks, 50),
        frame_mrr=calc_mrr(f_ranks),
        # Tolerant Frame-Level (Relaxed ±tolerance_frames)
        tol_frame_hit1=calc_hit(tf_ranks, 1),
        tol_frame_hit3=calc_hit(tf_ranks, 3),
        tol_frame_hit5=calc_hit(tf_ranks, 5),
        tol_frame_hit10=calc_hit(tf_ranks, 10),
        tol_frame_hit20=calc_hit(tf_ranks, 20),
        tol_frame_hit50=calc_hit(tf_ranks, 50),
        tol_frame_mrr5=calc_mrr(tf_ranks, 5),
        tol_frame_mrr10=calc_mrr(tf_ranks, 10),
        tol_frame_mrr20=calc_mrr(tf_ranks, 20),
        tol_frame_mrr50=calc_mrr(tf_ranks, 50),
        tol_frame_mrr=calc_mrr(tf_ranks),
        # Video-Level
        video_hit1=calc_hit(v_ranks, 1),
        video_hit3=calc_hit(v_ranks, 3),
        video_hit5=calc_hit(v_ranks, 5),
        video_hit10=calc_hit(v_ranks, 10),
        video_hit20=calc_hit(v_ranks, 20),
        video_hit50=calc_hit(v_ranks, 50),
        video_mrr5=calc_mrr(v_ranks, 5),
        video_mrr10=calc_mrr(v_ranks, 10),
        video_mrr20=calc_mrr(v_ranks, 20),
        video_mrr50=calc_mrr(v_ranks, 50),
        video_mrr=calc_mrr(v_ranks),
        query_results=query_results,
    )


async def evaluate_retrieval(
    embedding_model_name: str,
    gt_rows: list[dict[str, Any]],
    *,
    reranker_model_name: str | None = None,
    rerank_mode: str = "text",
    embed_device: str = "cpu",
    reranker_device: str = "cuda",
    top_k: int = 50,
    tolerance_frames: int = 4,
    collection: str | None = None,
    vector_name: str = "qwen",
    batch_size: int = 16,
) -> tuple[EvaluationReport, EvaluationReport | None]:
    settings = get_settings()
    coll = collection or settings.qdrant.collection
    resolved_embed_dev = resolve_device(embed_device)
    resolved_rerank_dev = resolve_device(reranker_device)

    # 1. Encode queries on embed_device (CPU/GPU)
    st_model = load_sentence_transformer(embedding_model_name, resolved_embed_dev)
    client = get_qdrant_client()
    qdrant_target = settings.qdrant.url or f"{settings.qdrant.host}:{settings.qdrant.port}"
    logger.info(
        f"Target Qdrant endpoint: {qdrant_target} | Collection: {coll} | Vector: {vector_name}"
    )

    captions = [r["caption"] for r in gt_rows]
    logger.info(
        f"Encoding {len(captions)} queries on {resolved_embed_dev} with batch_size={batch_size}..."
    )
    t0 = time.perf_counter()

    embeddings = st_model.encode(
        captions,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    if hasattr(embeddings, "tolist"):
        vectors = embeddings.tolist()
    else:
        vectors = [list(v) for v in embeddings]

    # Free up embedding model memory immediately
    del st_model
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    # 2. Retrieve Stage-1 candidates from Qdrant
    logger.info(f"Querying Qdrant collection '{coll}' for top-{top_k} nearest candidates...")
    candidates_per_query: list[list[Any]] = []

    for i, (row, vec) in enumerate(zip(gt_rows, vectors)):
        response = await client.query_points(
            collection_name=coll,
            query=vec,
            using=vector_name,
            limit=top_k,
            with_payload=True,
        )
        candidates_per_query.append(response.points)

    stage1_duration = time.perf_counter() - t0

    # 3. Compute Stage-1 (Before Rerank) query results
    stage1_results: list[QueryResult] = []
    for row, points in zip(gt_rows, candidates_per_query):
        gt_vid = row["video_id"]
        gt_fid = row["frame_id"]
        gt_fname = row["frame_name"]

        qr = QueryResult(
            query_id=row["query_id"],
            caption=row["caption"],
            gt_video_id=gt_vid,
            gt_frame_id=gt_fid if isinstance(gt_fid, int) else 0,
            gt_frame_name=gt_fname,
        )

        for rank, pt in enumerate(points, start=1):
            p = pt.payload or {}
            ret_vid = str(p.get("video_id", "")).strip()
            ret_fid_raw = p.get("frame_id")
            ret_fname = str(p.get("frame_name", "")).strip()

            if rank == 1:
                qr.top1_video_id = ret_vid
                qr.top1_frame_id = ret_fid_raw
                qr.top1_frame_name = ret_fname
                qr.top1_score = float(pt.score)

            is_video_match = ret_vid == gt_vid
            is_exact_frame_match = False
            is_tolerant_frame_match = False
            if is_video_match:
                try:
                    diff = abs(int(ret_fid_raw) - int(gt_fid))
                    is_exact_frame_match = (diff == 0) or (ret_fname == gt_fname and bool(gt_fname))
                    is_tolerant_frame_match = (diff <= tolerance_frames) or is_exact_frame_match
                except Exception:
                    is_exact_frame_match = ret_fname == gt_fname and bool(gt_fname)
                    is_tolerant_frame_match = is_exact_frame_match

            if is_video_match and qr.video_rank is None:
                qr.video_rank = rank
            if is_exact_frame_match and qr.frame_rank is None:
                qr.frame_rank = rank
            if is_tolerant_frame_match and qr.tolerant_frame_rank is None:
                qr.tolerant_frame_rank = rank

        stage1_results.append(qr)

    report_before = compute_metrics(
        stage1_results,
        len(gt_rows),
        embedding_model_name,
        stage1_duration,
        tolerance_frames=tolerance_frames,
    )

    if not reranker_model_name:
        return report_before, None

    # 4. Stage-2 Reranking with Qwen3-VL (Visual mode or Text mode)
    logger.info(
        f"Reranking top-{top_k} candidates for {len(gt_rows)} queries with {reranker_model_name} (Mode: {rerank_mode})..."
    )
    t_rerank_start = time.perf_counter()

    # Build ALL (query, document/image) pairs for batch prediction
    pair_map: list[tuple[int, int]] = []  # (query_idx, candidate_idx)
    for qi, (row, points) in enumerate(zip(gt_rows, candidates_per_query)):
        for ci in range(len(points)):
            pair_map.append((qi, ci))

    if rerank_mode == "visual":
        from ml.image_cache import get_image_cache
        from ml.qwen_visual_reranker import Qwen3VLVisualReranker

        visual_reranker = Qwen3VLVisualReranker(
            model_name=reranker_model_name, device=resolved_rerank_dev
        )
        image_cache = get_image_cache()
        logger.info(
            f"  Fetching thumbnails from Redis/MinIO for {len(pair_map)} candidate keyframes..."
        )
        items_to_fetch = [
            (
                str((candidates_per_query[qi][ci].payload or {}).get("video_id", "")).strip(),
                str((candidates_per_query[qi][ci].payload or {}).get("frame_name", "")).strip(),
            )
            for qi, ci in pair_map
        ]
        images = await image_cache.get_images_batch(items_to_fetch)
        all_pairs: list[tuple[str, Any]] = []
        for (qi, ci), img in zip(pair_map, images):
            query_text = gt_rows[qi]["caption"]
            if img is not None:
                all_pairs.append((query_text, img))
            else:
                doc_text = build_candidate_text(candidates_per_query[qi][ci].payload or {})
                all_pairs.append((query_text, doc_text))

        logger.info(
            f"  Predicting Visual Relevance (Qwen3-VL yes/no softmax) for {len(all_pairs)} pairs..."
        )
        all_scores = visual_reranker.score_pairs(all_pairs, batch_size=8, show_progress_bar=True)
    else:
        cross_encoder = load_cross_encoder(reranker_model_name, resolved_rerank_dev)
        all_pairs = []
        for qi, ci in pair_map:
            query_text = gt_rows[qi]["caption"]
            doc_text = build_candidate_text(candidates_per_query[qi][ci].payload or {})
            all_pairs.append((query_text, doc_text))

        logger.info(f"  Predicting text scores for {len(all_pairs)} pairs in batch...")
        all_scores = cross_encoder.predict(all_pairs, batch_size=64, show_progress_bar=True)

    logger.info(f"  Reranking prediction done in {time.perf_counter() - t_rerank_start:.2f}s")

    # Group scores back per query and sort by score descending
    from collections import defaultdict

    query_scores: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for (qi, ci), score in zip(pair_map, all_scores):
        query_scores[qi].append((ci, float(score)))

    stage2_results: list[QueryResult] = []
    for qi, row in enumerate(gt_rows):
        gt_vid = row["video_id"]
        gt_fid = row["frame_id"]
        gt_fname = row["frame_name"]
        points = candidates_per_query[qi]

        # Sort candidates by cross-encoder score descending
        ranked = sorted(query_scores[qi], key=lambda x: x[1], reverse=True)

        qr = QueryResult(
            query_id=row["query_id"],
            caption=row["caption"],
            gt_video_id=gt_vid,
            gt_frame_id=gt_fid if isinstance(gt_fid, int) else 0,
            gt_frame_name=gt_fname,
        )

        for new_rank, (orig_idx, score) in enumerate(ranked, start=1):
            pt = points[orig_idx]
            p = pt.payload or {}
            ret_vid = str(p.get("video_id", "")).strip()
            ret_fid_raw = p.get("frame_id")
            ret_fname = str(p.get("frame_name", "")).strip()

            if new_rank == 1:
                qr.top1_video_id = ret_vid
                qr.top1_frame_id = ret_fid_raw
                qr.top1_frame_name = ret_fname
                qr.top1_score = score

            is_video_match = ret_vid == gt_vid
            is_exact_frame_match = False
            is_tolerant_frame_match = False
            if is_video_match:
                try:
                    diff = abs(int(ret_fid_raw) - int(gt_fid))
                    is_exact_frame_match = (diff == 0) or (ret_fname == gt_fname and bool(gt_fname))
                    is_tolerant_frame_match = (diff <= tolerance_frames) or is_exact_frame_match
                except Exception:
                    is_exact_frame_match = ret_fname == gt_fname and bool(gt_fname)
                    is_tolerant_frame_match = is_exact_frame_match

            if is_video_match and qr.video_rank is None:
                qr.video_rank = new_rank
            if is_exact_frame_match and qr.frame_rank is None:
                qr.frame_rank = new_rank
            if is_tolerant_frame_match and qr.tolerant_frame_rank is None:
                qr.tolerant_frame_rank = new_rank

        stage2_results.append(qr)

    stage2_duration = time.perf_counter() - t_rerank_start
    report_after = compute_metrics(
        stage2_results,
        len(gt_rows),
        reranker_model_name,
        stage2_duration,
        tolerance_frames=tolerance_frames,
    )

    return report_before, report_after


def format_single_table(report: EvaluationReport) -> str:
    headers = [
        "Granularity",
        "Hit@1",
        "Hit@3",
        "Hit@5",
        "Hit@10",
        "Hit@20",
        "Hit@50",
        "MRR@5",
        "MRR@10",
        "MRR@20",
        "MRR (Full)",
    ]
    rows = [
        [
            "🎬 Video-Level (Đúng Video)",
            f"{report.video_hit1 * 100:.2f}%",
            f"{report.video_hit3 * 100:.2f}%",
            f"{report.video_hit5 * 100:.2f}%",
            f"{report.video_hit10 * 100:.2f}%",
            f"{report.video_hit20 * 100:.2f}%",
            f"{report.video_hit50 * 100:.2f}%",
            f"{report.video_mrr5:.4f}",
            f"{report.video_mrr10:.4f}",
            f"{report.video_mrr20:.4f}",
            f"{report.video_mrr:.4f}",
        ],
        [
            f"🎯 Frame-Tolerant (±{report.tolerance_frames}f / ~2s)",
            f"{report.tol_frame_hit1 * 100:.2f}%",
            f"{report.tol_frame_hit3 * 100:.2f}%",
            f"{report.tol_frame_hit5 * 100:.2f}%",
            f"{report.tol_frame_hit10 * 100:.2f}%",
            f"{report.tol_frame_hit20 * 100:.2f}%",
            f"{report.tol_frame_hit50 * 100:.2f}%",
            f"{report.tol_frame_mrr5:.4f}",
            f"{report.tol_frame_mrr10:.4f}",
            f"{report.tol_frame_mrr20:.4f}",
            f"{report.tol_frame_mrr:.4f}",
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            f"{report.frame_hit1 * 100:.2f}%",
            f"{report.frame_hit3 * 100:.2f}%",
            f"{report.frame_hit5 * 100:.2f}%",
            f"{report.frame_hit10 * 100:.2f}%",
            f"{report.frame_hit20 * 100:.2f}%",
            f"{report.frame_hit50 * 100:.2f}%",
            f"{report.frame_mrr5:.4f}",
            f"{report.frame_mrr10:.4f}",
            f"{report.frame_mrr20:.4f}",
            f"{report.frame_mrr:.4f}",
        ],
    ]
    return _format_table(headers, rows)


def format_comparison_table(
    base: EvaluationReport,
    fine: EvaluationReport,
    base_name: str = "Trước Rerank (Vector)",
    fine_name: str = "Sau Rerank (Cross-Encoder)",
) -> str:
    def diff_pct(v_after: float, v_before: float) -> str:
        d = (v_after - v_before) * 100
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.2f}%"

    def diff_num(v_after: float, v_before: float) -> str:
        d = v_after - v_before
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.4f}"

    headers = [
        "Cấp độ đánh giá",
        "Chỉ số (Metric)",
        base_name,
        fine_name,
        "Độ cải thiện (Delta)",
    ]

    tol_label = f"🎯 Frame-Tolerant (±{fine.tolerance_frames}f / ~2s)"

    table_data = [
        # Video Level
        [
            "🎬 Video-Level (Đúng Video)",
            "Hit@1",
            f"{base.video_hit1 * 100:.2f}%",
            f"{fine.video_hit1 * 100:.2f}%",
            diff_pct(fine.video_hit1, base.video_hit1),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "Hit@3",
            f"{base.video_hit3 * 100:.2f}%",
            f"{fine.video_hit3 * 100:.2f}%",
            diff_pct(fine.video_hit3, base.video_hit3),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "Hit@5",
            f"{base.video_hit5 * 100:.2f}%",
            f"{fine.video_hit5 * 100:.2f}%",
            diff_pct(fine.video_hit5, base.video_hit5),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "Hit@10",
            f"{base.video_hit10 * 100:.2f}%",
            f"{fine.video_hit10 * 100:.2f}%",
            diff_pct(fine.video_hit10, base.video_hit10),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "Hit@20",
            f"{base.video_hit20 * 100:.2f}%",
            f"{fine.video_hit20 * 100:.2f}%",
            diff_pct(fine.video_hit20, base.video_hit20),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "Hit@50",
            f"{base.video_hit50 * 100:.2f}%",
            f"{fine.video_hit50 * 100:.2f}%",
            diff_pct(fine.video_hit50, base.video_hit50),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "MRR@5",
            f"{base.video_mrr5:.4f}",
            f"{fine.video_mrr5:.4f}",
            diff_num(fine.video_mrr5, base.video_mrr5),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "MRR@10",
            f"{base.video_mrr10:.4f}",
            f"{fine.video_mrr10:.4f}",
            diff_num(fine.video_mrr10, base.video_mrr10),
        ],
        [
            "🎬 Video-Level (Đúng Video)",
            "MRR (Full)",
            f"{base.video_mrr:.4f}",
            f"{fine.video_mrr:.4f}",
            diff_num(fine.video_mrr, base.video_mrr),
        ],
        # Tolerant Frame Level
        [
            tol_label,
            "Hit@1",
            f"{base.tol_frame_hit1 * 100:.2f}%",
            f"{fine.tol_frame_hit1 * 100:.2f}%",
            diff_pct(fine.tol_frame_hit1, base.tol_frame_hit1),
        ],
        [
            tol_label,
            "Hit@3",
            f"{base.tol_frame_hit3 * 100:.2f}%",
            f"{fine.tol_frame_hit3 * 100:.2f}%",
            diff_pct(fine.tol_frame_hit3, base.tol_frame_hit3),
        ],
        [
            tol_label,
            "Hit@5",
            f"{base.tol_frame_hit5 * 100:.2f}%",
            f"{fine.tol_frame_hit5 * 100:.2f}%",
            diff_pct(fine.tol_frame_hit5, base.tol_frame_hit5),
        ],
        [
            tol_label,
            "Hit@10",
            f"{base.tol_frame_hit10 * 100:.2f}%",
            f"{fine.tol_frame_hit10 * 100:.2f}%",
            diff_pct(fine.tol_frame_hit10, base.tol_frame_hit10),
        ],
        [
            tol_label,
            "Hit@20",
            f"{base.tol_frame_hit20 * 100:.2f}%",
            f"{fine.tol_frame_hit20 * 100:.2f}%",
            diff_pct(fine.tol_frame_hit20, base.tol_frame_hit20),
        ],
        [
            tol_label,
            "Hit@50",
            f"{base.tol_frame_hit50 * 100:.2f}%",
            f"{fine.tol_frame_hit50 * 100:.2f}%",
            diff_pct(fine.tol_frame_hit50, base.tol_frame_hit50),
        ],
        [
            tol_label,
            "MRR@5",
            f"{base.tol_frame_mrr5:.4f}",
            f"{fine.tol_frame_mrr5:.4f}",
            diff_num(fine.tol_frame_mrr5, base.tol_frame_mrr5),
        ],
        [
            tol_label,
            "MRR@10",
            f"{base.tol_frame_mrr10:.4f}",
            f"{fine.tol_frame_mrr10:.4f}",
            diff_num(fine.tol_frame_mrr10, base.tol_frame_mrr10),
        ],
        [
            tol_label,
            "MRR (Full)",
            f"{base.tol_frame_mrr:.4f}",
            f"{fine.tol_frame_mrr:.4f}",
            diff_num(fine.tol_frame_mrr, base.tol_frame_mrr),
        ],
        # Frame Level Exact
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "Hit@1",
            f"{base.frame_hit1 * 100:.2f}%",
            f"{fine.frame_hit1 * 100:.2f}%",
            diff_pct(fine.frame_hit1, base.frame_hit1),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "Hit@3",
            f"{base.frame_hit3 * 100:.2f}%",
            f"{fine.frame_hit3 * 100:.2f}%",
            diff_pct(fine.frame_hit3, base.frame_hit3),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "Hit@5",
            f"{base.frame_hit5 * 100:.2f}%",
            f"{fine.frame_hit5 * 100:.2f}%",
            diff_pct(fine.frame_hit5, base.frame_hit5),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "Hit@10",
            f"{base.frame_hit10 * 100:.2f}%",
            f"{fine.frame_hit10 * 100:.2f}%",
            diff_pct(fine.frame_hit10, base.frame_hit10),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "Hit@20",
            f"{base.frame_hit20 * 100:.2f}%",
            f"{fine.frame_hit20 * 100:.2f}%",
            diff_pct(fine.frame_hit20, base.frame_hit20),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "Hit@50",
            f"{base.frame_hit50 * 100:.2f}%",
            f"{fine.frame_hit50 * 100:.2f}%",
            diff_pct(fine.frame_hit50, base.frame_hit50),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "MRR@5",
            f"{base.frame_mrr5:.4f}",
            f"{fine.frame_mrr5:.4f}",
            diff_num(fine.frame_mrr5, base.frame_mrr5),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "MRR@10",
            f"{base.frame_mrr10:.4f}",
            f"{fine.frame_mrr10:.4f}",
            diff_num(fine.frame_mrr10, base.frame_mrr10),
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame)",
            "MRR (Full)",
            f"{base.frame_mrr:.4f}",
            f"{fine.frame_mrr:.4f}",
            diff_num(fine.frame_mrr, base.frame_mrr),
        ],
    ]
    return _format_table(headers, table_data)


def generate_markdown_report(
    base_report: EvaluationReport,
    fine_report: EvaluationReport,
    dataset_path: Path | str,
    top_k: int,
    output_path: Path | str,
) -> str:
    base_label = base_report.model_name.split("/")[-1]
    fine_label = fine_report.model_name.split("/")[-1]
    comp_table = format_comparison_table(
        base_report,
        fine_report,
        base_name=f"Trước Rerank ({base_label})",
        fine_name=f"Sau Rerank ({fine_label})",
    )

    improved_frames = 0
    degraded_frames = 0
    equal_frames = 0
    improved_tol_frames = 0
    degraded_tol_frames = 0
    equal_tol_frames = 0
    improved_videos = 0
    degraded_videos = 0
    equal_videos = 0

    shifts = []
    for q_before, q_after in zip(base_report.query_results, fine_report.query_results):
        r_f_b = q_before.frame_rank or 999
        r_f_a = q_after.frame_rank or 999
        if r_f_a < r_f_b:
            improved_frames += 1
        elif r_f_a > r_f_b:
            degraded_frames += 1
        else:
            equal_frames += 1

        r_tf_b = q_before.tolerant_frame_rank or 999
        r_tf_a = q_after.tolerant_frame_rank or 999
        if r_tf_a < r_tf_b:
            improved_tol_frames += 1
        elif r_tf_a > r_tf_b:
            degraded_tol_frames += 1
        else:
            equal_tol_frames += 1

        r_v_b = q_before.video_rank or 999
        r_v_a = q_after.video_rank or 999
        if r_v_a < r_v_b:
            improved_videos += 1
        elif r_v_a > r_v_b:
            degraded_videos += 1
        else:
            equal_videos += 1

        diff_tf = r_tf_b - r_tf_a
        shifts.append(
            {
                "query_id": q_before.query_id,
                "caption": q_before.caption,
                "gt_video": q_before.gt_video_id,
                "gt_frame": q_before.gt_frame_name,
                "before_v_rank": q_before.video_rank or "-",
                "after_v_rank": q_after.video_rank or "-",
                "before_tf_rank": q_before.tolerant_frame_rank or "-",
                "after_tf_rank": q_after.tolerant_frame_rank or "-",
                "before_f_rank": q_before.frame_rank or "-",
                "after_f_rank": q_after.frame_rank or "-",
                "diff_tf": diff_tf,
            }
        )

    shifts.sort(key=lambda x: x["diff_tf"], reverse=True)
    sample_rows = []
    for s in shifts[:15]:
        sample_rows.append(
            [
                f"#{s['query_id']}",
                f"{s['caption'][:50]}...",
                f"{s['gt_video']}",
                f"{s['gt_frame']}",
                f"#{s['before_v_rank']} ➔ #{s['after_v_rank']}",
                f"#{s['before_tf_rank']} ➔ #{s['after_tf_rank']}",
                f"#{s['before_f_rank']} ➔ #{s['after_f_rank']}",
            ]
        )
    shifts_table = _format_table(
        [
            "Query ID",
            "Câu truy vấn (Caption)",
            "GT Video",
            "GT Frame",
            "Video Rank",
            f"Tolerant Rank (±{fine_report.tolerance_frames}f)",
            "Exact Frame Rank",
        ],
        sample_rows,
    )

    md_lines = [
        f"# 📊 Báo Cáo Đánh Giá Hiệu Năng: Trước & Sau Rerank (Top-K = {top_k}, Tolerance = ±{fine_report.tolerance_frames} frames)",
        "",
        f"> **Tập dữ liệu Ground Truth:** `{dataset_path}`",
        f"> **Tổng số câu truy vấn kiểm thử:** `{base_report.total_queries}` queries",
        f"> **Mô hình Giai đoạn 1 (First-Stage Vector Search):** `{base_report.model_name}`",
        f"> **Mô hình Giai đoạn 2 (Second-Stage Cross-Encoder Reranker):** `{fine_report.model_name}`",
        f"> **Thời gian thực thi:** Vector Search: `{base_report.duration_s:.2f}s` | Reranking: `{fine_report.duration_s:.2f}s`",
        "",
        "---",
        "",
        "## 1. Bảng So Sánh Tổng Hợp (Retrieval Metrics: Before vs After Rerank)",
        "",
        comp_table,
        "",
        "---",
        "",
        "## 2. Phân Tích Thống Kê Thay Đổi Thứ Hạng (Ranking Shift Analysis)",
        "",
        f"* **🎯 Cấp độ Frame-Tolerant (±{fine_report.tolerance_frames} frames / ~2 giây):**",
        f"  * **Cải thiện thứ hạng (Improved):** `{improved_tol_frames}/{base_report.total_queries}` queries (`{improved_tol_frames / base_report.total_queries * 100:.1f}%`)",
        f"  * **Không đổi (Unchanged):** `{equal_tol_frames}/{base_report.total_queries}` queries (`{equal_tol_frames / base_report.total_queries * 100:.1f}%`)",
        f"  * **Thứ hạng giảm (Degraded):** `{degraded_tol_frames}/{base_report.total_queries}` queries (`{degraded_tol_frames / base_report.total_queries * 100:.1f}%`)",
        "",
        "* **🖼️ Cấp độ Frame-Exact (Đúng chính xác Frame):**",
        f"  * **Cải thiện thứ hạng (Improved):** `{improved_frames}/{base_report.total_queries}` queries (`{improved_frames / base_report.total_queries * 100:.1f}%`)",
        f"  * **Không đổi (Unchanged):** `{equal_frames}/{base_report.total_queries}` queries (`{equal_frames / base_report.total_queries * 100:.1f}%`)",
        f"  * **Thứ hạng giảm (Degraded):** `{degraded_frames}/{base_report.total_queries}` queries (`{degraded_frames / base_report.total_queries * 100:.1f}%`)",
        "",
        "* **🎬 Cấp độ Video-Level (Đúng Video cha):**",
        f"  * **Cải thiện thứ hạng (Improved):** `{improved_videos}/{base_report.total_queries}` queries (`{improved_videos / base_report.total_queries * 100:.1f}%`)",
        f"  * **Không đổi (Unchanged):** `{equal_videos}/{base_report.total_queries}` queries (`{equal_videos / base_report.total_queries * 100:.1f}%`)",
        f"  * **Thứ hạng giảm (Degraded):** `{degraded_videos}/{base_report.total_queries}` queries (`{degraded_videos / base_report.total_queries * 100:.1f}%`)",
        "",
        "---",
        "",
        "## 3. Mẫu Một Số Câu Truy Vấn Được Cải Thiện Thứ Hạng Nổi Bật",
        "",
        shifts_table,
        "",
        "---",
        "",
        "## 4. Đánh Giá & Nhận Xét Chuyên Môn",
        "",
        "1. **Hiệu năng First-Stage Vector Search:**",
        f"   - Vector Embedding của Qwen 2B cho khả năng tìm kiếm video thô rất tốt với **Hit@50 = {base_report.video_hit50 * 100:.2f}%** và **Hit@1 = {base_report.video_hit1 * 100:.2f}%**.",
        f"2. **Hiệu quả Reranker trên Metric nới lỏng (Tolerance = ±{fine_report.tolerance_frames} frames):**",
        f"   - Với độ lệch cho phép {fine_report.tolerance_frames} frames (~2 giây), Reranker đạt **Hit@1 = {fine_report.tol_frame_hit1 * 100:.2f}%** (thay đổi {((fine_report.tol_frame_hit1 - base_report.tol_frame_hit1) * 100):+.2f}% so với trước khi rerank).",
        f"   - Chỉ số **MRR Tolerant** đạt **{fine_report.tol_frame_mrr:.4f}**, phản ánh chân thực trải nghiệm tra cứu video trong thực tế khi frame trả về nằm đúng phân đoạn hành động.",
        "",
    ]
    md_content = "\n".join(md_lines)

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"Markdown report generated successfully at: {out_p.resolve()}")
    return md_content


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Qwen Embedding & Reranker (HitRate & MRR) on Golden Set"
    )
    parser.add_argument(
        "--csv", default="eval/golden_set/eval.csv", help="Path to ground truth CSV"
    )
    parser.add_argument(
        "--base-model",
        default="Qwen/Qwen3-VL-Embedding-2B",
        help="Pretrained baseline Qwen embedding model",
    )
    parser.add_argument(
        "--finetuned-model", default=None, help="Fine-tuned Qwen checkpoint path or HF repo ID"
    )
    parser.add_argument(
        "--reranker-model", default="Qwen/Qwen3-VL-Reranker-2B", help="Reranker model name or path"
    )
    parser.add_argument(
        "--rerank-mode",
        choices=["text", "visual"],
        default="visual",
        help="Rerank mode: 'visual' (look at actual keyframe images) or 'text' (look at metadata captions)",
    )
    parser.add_argument(
        "--eval-rerank",
        action="store_true",
        default=True,
        help="Evaluate before and after reranker",
    )
    parser.add_argument(
        "--tolerance-frames",
        type=int,
        default=4,
        help="Tolerance window frames for relaxed frame hit evaluation (default: 4, ~2s)",
    )
    parser.add_argument("--collection", default="Scences", help="Qdrant collection name")
    parser.add_argument("--vector-name", default="qwen", help="Vector name in Qdrant")
    parser.add_argument(
        "--top-k", type=int, default=10, help="Retrieval top K cutoff (default: 10)"
    )
    parser.add_argument(
        "--embed-device",
        default="cpu",
        help="Query embedding device: cpu, cuda, auto (default: cpu)",
    )
    parser.add_argument(
        "--rerank-device",
        default="cuda",
        help="Reranker inference device: cuda, cpu, auto (default: cuda)",
    )
    parser.add_argument("--batch-size", type=int, default=16, help="Query encoding batch size")
    parser.add_argument(
        "--output-json",
        default="eval/reports/eval_results.json",
        help="Save detailed report to JSON",
    )
    parser.add_argument(
        "--output-markdown",
        default="eval/reports/eval_rerank_report.md",
        help="Save markdown comparison table to file",
    )

    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = (
            Path(__file__).resolve().parent / "golden_set" / "eval.csv"
            if not Path(args.csv).exists()
            else Path(args.csv)
        )

    print("\n=======================================================")
    print(
        f"🎯 QWEN BENCHMARK — GOLDEN SET EVALUATION (TOP-K = {args.top_k}, TOLERANCE = ±{args.tolerance_frames} frames, MODE = {args.rerank_mode.upper()})"
    )
    print(f"   Evaluation Dataset: {csv_path}")
    print(f"   Qdrant Collection: {args.collection} (Vector: {args.vector_name})")
    print(f"   Embedding Model: {args.base_model} (Device: {args.embed_device})")
    print(
        f"   Reranker Model: {args.reranker_model if args.eval_rerank else None} (Mode: {args.rerank_mode.upper()}, Device: {args.rerank_device})"
    )
    print(f"   Top-K Cutoff: {args.top_k} | Tolerance: ±{args.tolerance_frames} frames")
    print("=======================================================\n")

    gt_rows = load_ground_truth(csv_path)
    print(f"Loaded {len(gt_rows)} benchmark queries from CSV.\n")

    reranker_target = args.reranker_model if args.eval_rerank else None
    report_before, report_after = asyncio.run(
        evaluate_retrieval(
            args.base_model,
            gt_rows,
            reranker_model_name=reranker_target,
            rerank_mode=args.rerank_mode,
            embed_device=args.embed_device,
            reranker_device=args.rerank_device,
            top_k=args.top_k,
            tolerance_frames=args.tolerance_frames,
            collection=args.collection,
            vector_name=args.vector_name,
            batch_size=args.batch_size,
        )
    )

    print(f"\n✅ Giai đoạn 1: Trước Rerank (Vector Search - {report_before.duration_s:.2f}s):\n")
    print(format_single_table(report_before))

    if report_after:
        print(
            f"\n✅ Giai đoạn 2: Sau Rerank ({args.reranker_model} - {report_after.duration_s:.2f}s):\n"
        )
        print(format_single_table(report_after))

        print("\n\n=======================================================")
        print(
            f"📊 BẢNG SO SÁNH: TRƯỚC RERANK vs SAU RERANK (TOP-K = {args.top_k}, TOLERANCE = ±{args.tolerance_frames} frames)"
        )
        print("=======================================================\n")
        base_label = args.base_model.split("/")[-1]
        fine_label = args.reranker_model.split("/")[-1]
        comp_md = format_comparison_table(
            report_before,
            report_after,
            base_name=f"Trước Rerank ({base_label})",
            fine_name=f"Sau Rerank ({fine_label})",
        )
        print(comp_md)

        if args.output_markdown:
            generate_markdown_report(
                report_before,
                report_after,
                dataset_path=csv_path,
                top_k=args.top_k,
                output_path=args.output_markdown,
            )
            print(f"\n📄 Đã tạo và lưu Báo Cáo Markdown tại: {args.output_markdown}")

    if args.output_json:
        out_j = Path(args.output_json)
        out_j.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "dataset": str(csv_path),
            "total_queries": len(gt_rows),
            "top_k": args.top_k,
            "tolerance_frames": args.tolerance_frames,
            "before_rerank": {
                "model": report_before.model_name,
                "video_metrics": {
                    "hit@1": report_before.video_hit1,
                    "hit@3": report_before.video_hit3,
                    "hit@5": report_before.video_hit5,
                    "hit@10": report_before.video_hit10,
                    "hit@20": report_before.video_hit20,
                    "hit@50": report_before.video_hit50,
                    "mrr@5": report_before.video_mrr5,
                    "mrr@10": report_before.video_mrr10,
                    "mrr@20": report_before.video_mrr20,
                    "mrr_full": report_before.video_mrr,
                },
                "tolerant_frame_metrics": {
                    "hit@1": report_before.tol_frame_hit1,
                    "hit@3": report_before.tol_frame_hit3,
                    "hit@5": report_before.tol_frame_hit5,
                    "hit@10": report_before.tol_frame_hit10,
                    "hit@20": report_before.tol_frame_hit20,
                    "hit@50": report_before.tol_frame_hit50,
                    "mrr@5": report_before.tol_frame_mrr5,
                    "mrr@10": report_before.tol_frame_mrr10,
                    "mrr@20": report_before.tol_frame_mrr20,
                    "mrr_full": report_before.tol_frame_mrr,
                },
                "exact_frame_metrics": {
                    "hit@1": report_before.frame_hit1,
                    "hit@3": report_before.frame_hit3,
                    "hit@5": report_before.frame_hit5,
                    "hit@10": report_before.frame_hit10,
                    "hit@20": report_before.frame_hit20,
                    "hit@50": report_before.frame_hit50,
                    "mrr@5": report_before.frame_mrr5,
                    "mrr@10": report_before.frame_mrr10,
                    "mrr@20": report_before.frame_mrr20,
                    "mrr_full": report_before.frame_mrr,
                },
            },
        }
        if report_after:
            data["after_rerank"] = {
                "model": report_after.model_name,
                "video_metrics": {
                    "hit@1": report_after.video_hit1,
                    "hit@3": report_after.video_hit3,
                    "hit@5": report_after.video_hit5,
                    "hit@10": report_after.video_hit10,
                    "hit@20": report_after.video_hit20,
                    "hit@50": report_after.video_hit50,
                    "mrr@5": report_after.video_mrr5,
                    "mrr@10": report_after.video_mrr10,
                    "mrr@20": report_after.video_mrr20,
                    "mrr_full": report_after.video_mrr,
                },
                "tolerant_frame_metrics": {
                    "hit@1": report_after.tol_frame_hit1,
                    "hit@3": report_after.tol_frame_hit3,
                    "hit@5": report_after.tol_frame_hit5,
                    "hit@10": report_after.tol_frame_hit10,
                    "hit@20": report_after.tol_frame_hit20,
                    "hit@50": report_after.tol_frame_hit50,
                    "mrr@5": report_after.tol_frame_mrr5,
                    "mrr@10": report_after.tol_frame_mrr10,
                    "mrr@20": report_after.tol_frame_mrr20,
                    "mrr_full": report_after.tol_frame_mrr,
                },
                "exact_frame_metrics": {
                    "hit@1": report_after.frame_hit1,
                    "hit@3": report_after.frame_hit3,
                    "hit@5": report_after.frame_hit5,
                    "hit@10": report_after.frame_hit10,
                    "hit@20": report_after.frame_hit20,
                    "hit@50": report_after.frame_hit50,
                    "mrr@5": report_after.frame_mrr5,
                    "mrr@10": report_after.frame_mrr10,
                    "mrr@20": report_after.frame_mrr20,
                    "mrr_full": report_after.frame_mrr,
                },
            }
        with open(out_j, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"📊 Đã lưu dữ liệu JSON chi tiết tại: {args.output_json}")


if __name__ == "__main__":
    main()
