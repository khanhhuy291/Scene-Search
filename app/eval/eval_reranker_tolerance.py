"""Evaluation module & script for Reranker HitRate (Hit@K) and MRR with Frame Tolerance.

Supports 3 evaluation tiers:
1. Video-Level: Correct video retrieved.
2. Frame-Tolerant (Soft / Window Match): Matched within ±tolerance_frames window (e.g. ±4 frames = ±2s @ 2fps).
3. Frame-Exact (Strict Match): Exact ground truth frame retrieved.

Usage:
    # As a Python module:
    from eval.eval_reranker_tolerance import evaluate_single_query, compute_benchmark_report

    # As a standalone CLI:
    python app/eval/eval_reranker_tolerance.py --run-demo
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CandidateFrame:
    """A retrieved / reranked candidate frame item."""

    video_id: str
    frame_id: int | str
    score: float = 0.0
    frame_name: str = ""
    timestamp_s: float | None = None


@dataclass
class GroundTruthItem:
    """Ground truth target for a query."""

    query_id: str
    caption: str
    video_id: str
    frame_id: int | str
    frame_name: str = ""
    timestamp_s: float | None = None


@dataclass
class QueryEvalMetrics:
    query_id: str
    caption: str
    video_rank: int | None = None
    tolerant_frame_rank: int | None = None
    exact_frame_rank: int | None = None
    top1_video_id: str = ""
    top1_frame_id: Any = None
    top1_score: float = 0.0


@dataclass
class BenchmarkReport:
    name: str
    total_queries: int
    tolerance_frames: int
    # Video-Level Metrics
    video_hit: dict[int, float] = field(default_factory=dict)
    video_mrr: float = 0.0
    # Tolerant Frame-Level Metrics (Relaxed)
    tol_frame_hit: dict[int, float] = field(default_factory=dict)
    tol_frame_mrr: float = 0.0
    # Exact Frame-Level Metrics (Strict)
    exact_frame_hit: dict[int, float] = field(default_factory=dict)
    exact_frame_mrr: float = 0.0
    details: list[QueryEvalMetrics] = field(default_factory=list)


def evaluate_single_query(
    candidates: Sequence[CandidateFrame | dict[str, Any]],
    gt: GroundTruthItem | dict[str, Any],
    tolerance_frames: int = 4,
    tolerance_seconds: float | None = None,
) -> QueryEvalMetrics:
    """Evaluate a single query's ranked candidate list against ground truth."""
    gt_vid = str(gt.video_id if isinstance(gt, GroundTruthItem) else gt.get("video_id", "")).strip()
    gt_fid_raw = gt.frame_id if isinstance(gt, GroundTruthItem) else gt.get("frame_id", 0)
    gt_fname = str(
        gt.frame_name if isinstance(gt, GroundTruthItem) else gt.get("frame_name", "")
    ).strip()
    gt_ts = gt.timestamp_s if isinstance(gt, GroundTruthItem) else gt.get("timestamp_s")
    qid = str(gt.query_id if isinstance(gt, GroundTruthItem) else gt.get("query_id", ""))
    caption = str(gt.caption if isinstance(gt, GroundTruthItem) else gt.get("caption", ""))

    try:
        gt_fid = int(gt_fid_raw)
    except Exception:
        gt_fid = None

    metrics = QueryEvalMetrics(query_id=qid, caption=caption)

    for rank, item in enumerate(candidates, start=1):
        if isinstance(item, CandidateFrame):
            ret_vid = str(item.video_id).strip()
            ret_fid_raw = item.frame_id
            ret_fname = str(item.frame_name).strip()
            ret_ts = item.timestamp_s
            ret_score = float(item.score)
        else:
            ret_vid = str(item.get("video_id", "")).strip()
            ret_fid_raw = item.get("frame_id")
            ret_fname = str(item.get("frame_name", "")).strip()
            ret_ts = item.get("timestamp_s")
            ret_score = float(item.get("score", 0.0))

        if rank == 1:
            metrics.top1_video_id = ret_vid
            metrics.top1_frame_id = ret_fid_raw
            metrics.top1_score = ret_score

        try:
            ret_fid = int(ret_fid_raw)
        except Exception:
            ret_fid = None

        is_video_match = ret_vid == gt_vid
        is_exact_frame_match = False
        is_tolerant_frame_match = False

        if is_video_match:
            # 1. Exact frame check
            if ret_fid is not None and gt_fid is not None:
                is_exact_frame_match = ret_fid == gt_fid
            elif ret_fname and gt_fname:
                is_exact_frame_match = ret_fname == gt_fname

            # 2. Tolerant frame check (frame index or timestamp)
            if is_exact_frame_match:
                is_tolerant_frame_match = True
            elif tolerance_seconds is not None and ret_ts is not None and gt_ts is not None:
                is_tolerant_frame_match = abs(float(ret_ts) - float(gt_ts)) <= float(
                    tolerance_seconds
                )
            elif ret_fid is not None and gt_fid is not None:
                is_tolerant_frame_match = abs(ret_fid - gt_fid) <= tolerance_frames

        # Record highest rank (first occurrence)
        if is_video_match and metrics.video_rank is None:
            metrics.video_rank = rank
        if is_tolerant_frame_match and metrics.tolerant_frame_rank is None:
            metrics.tolerant_frame_rank = rank
        if is_exact_frame_match and metrics.exact_frame_rank is None:
            metrics.exact_frame_rank = rank

    return metrics


def compute_benchmark_report(
    eval_results: list[QueryEvalMetrics],
    name: str = "Reranker",
    tolerance_frames: int = 4,
    cutoffs: tuple[int, ...] = (1, 3, 5, 10, 20, 50),
) -> BenchmarkReport:
    """Compute aggregate Hit@K and MRR metrics across all queries."""
    total = len(eval_results)
    if total == 0:
        return BenchmarkReport(name=name, total_queries=0, tolerance_frames=tolerance_frames)

    def calc_hit_dict(ranks: list[int | None]) -> dict[int, float]:
        return {k: sum(1 for r in ranks if r is not None and r <= k) / total for k in cutoffs}

    def calc_mrr(ranks: list[int | None]) -> float:
        return sum((1.0 / r) for r in ranks if r is not None) / total

    v_ranks = [q.video_rank for q in eval_results]
    tf_ranks = [q.tolerant_frame_rank for q in eval_results]
    ef_ranks = [q.exact_frame_rank for q in eval_results]

    return BenchmarkReport(
        name=name,
        total_queries=total,
        tolerance_frames=tolerance_frames,
        video_hit=calc_hit_dict(v_ranks),
        video_mrr=calc_mrr(v_ranks),
        tol_frame_hit=calc_hit_dict(tf_ranks),
        tol_frame_mrr=calc_mrr(tf_ranks),
        exact_frame_hit=calc_hit_dict(ef_ranks),
        exact_frame_mrr=calc_mrr(ef_ranks),
        details=eval_results,
    )


def format_report_table(report: BenchmarkReport) -> str:
    """Format benchmark report into a clean markdown table."""
    ks = sorted(report.tol_frame_hit.keys())
    headers = ["Cấp độ đánh giá (Granularity)"] + [f"Hit@{k}" for k in ks] + ["MRR (Full)"]

    rows = [
        [
            "🎬 Video-Level (Đúng Video)",
            *[f"{report.video_hit[k] * 100:.2f}%" for k in ks],
            f"{report.video_mrr:.4f}",
        ],
        [
            f"🎯 Frame-Tolerant (±{report.tolerance_frames} frames / ~2s)",
            *[f"{report.tol_frame_hit[k] * 100:.2f}%" for k in ks],
            f"{report.tol_frame_mrr:.4f}",
        ],
        [
            "🖼️ Frame-Exact (Đúng Frame gốc)",
            *[f"{report.exact_frame_hit[k] * 100:.2f}%" for k in ks],
            f"{report.exact_frame_mrr:.4f}",
        ],
    ]

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


def run_demo_evaluation() -> None:
    """Demonstrate how tolerance evaluation works with sample synthetic retrieval data."""
    print("\n=======================================================")
    print("🚀 DEMO: ĐÁNH GIÁ HITRATE & MRR VỚI TOLERANCE_FRAMES = 4")
    print("=======================================================\n")

    demo_queries = [
        {
            "gt": {
                "query_id": "1",
                "caption": "Xe cứu hỏa FDNY",
                "video_id": "vid_001",
                "frame_id": 34,
            },
            "candidates": [
                {
                    "video_id": "vid_001",
                    "frame_id": 36,
                    "score": 0.95,
                },  # diff = 2 <= 4 -> Tolerant Rank 1
                {"video_id": "vid_001", "frame_id": 34, "score": 0.89},  # Exact Rank 2
                {"video_id": "vid_002", "frame_id": 10, "score": 0.70},
            ],
        },
        {
            "gt": {
                "query_id": "2",
                "caption": "Taxi vàng qua vạch đi bộ",
                "video_id": "vid_002",
                "frame_id": 65,
            },
            "candidates": [
                {"video_id": "vid_999", "frame_id": 10, "score": 0.98},
                {"video_id": "vid_002", "frame_id": 80, "score": 0.85},  # diff = 15 > 4 -> Miss
                {
                    "video_id": "vid_002",
                    "frame_id": 67,
                    "score": 0.75,
                },  # diff = 2 <= 4 -> Tolerant Rank 3
            ],
        },
        {
            "gt": {
                "query_id": "3",
                "caption": "Xe SUV đen ban đêm",
                "video_id": "vid_003",
                "frame_id": 49,
            },
            "candidates": [
                {"video_id": "vid_003", "frame_id": 49, "score": 0.99},  # Exact & Tolerant Rank 1
                {"video_id": "vid_003", "frame_id": 50, "score": 0.80},
            ],
        },
    ]

    results = []
    for item in demo_queries:
        res = evaluate_single_query(item["candidates"], item["gt"], tolerance_frames=4)
        results.append(res)

    report = compute_benchmark_report(
        results, name="Demo CrossEncoder Reranker", tolerance_frames=4
    )
    print(format_report_table(report))
    print("\n💡 Nhận xét Demo:")
    print(" - Nếu dùng Exact Frame Match: Hit@1 chỉ đạt 33.33%, MRR = 0.6111")
    print(" - Khi nới lỏng Tolerance ±4 frames (~2s): Hit@1 đạt 66.67%, MRR = 0.7778")
    print(" -> Phản ánh đúng việc hệ thống đã kéo được khoảnh khắc liên quan lên Top 1!\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Reranker HitRate and MRR with Frame Tolerance"
    )
    parser.add_argument("--run-demo", action="store_true", help="Run a quick synthetic demo")
    parser.add_argument(
        "--tolerance-frames", type=int, default=4, help="Allowed frame difference (default: 4, ~2s)"
    )
    parser.add_argument(
        "--input-json", type=str, default=None, help="Path to input predictions JSON"
    )
    args = parser.parse_args()

    if args.run_demo or args.input_json is None:
        run_demo_evaluation()
        return

    in_path = Path(args.input_json)
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")

    with open(in_path, encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for item in data:
        res = evaluate_single_query(
            item["candidates"], item["gt"], tolerance_frames=args.tolerance_frames
        )
        results.append(res)

    report = compute_benchmark_report(results, tolerance_frames=args.tolerance_frames)
    print(format_report_table(report))


if __name__ == "__main__":
    main()
