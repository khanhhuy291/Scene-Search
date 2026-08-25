#!/usr/bin/env python3
"""CLI runner for offline frame & caption embedding ingestion into Qdrant & MinIO.

Reads pre-generated VLM captions from JSONL, embeds frame images using SigLIP
and captions using BGE-M3, uploads media assets to MinIO, and indexes
named vectors into Qdrant. All parameters are dynamically parsed from argparse,
falling back to .env / app Settings when not specified.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Auto re-exec with project .venv if running system python missing dependencies
repo_root = Path(__file__).resolve().parents[3]
venv_python = repo_root / ".venv" / "bin" / "python"
if venv_python.exists() and sys.executable != str(venv_python):
    try:
        import loguru  # noqa: F401
    except ImportError:
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)

app_dir = Path(__file__).resolve().parents[2]

for p in (str(app_dir), str(repo_root)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from pipelines.ingestion.offline_embedder import OfflineEmbedderPipeline
except ModuleNotFoundError:
    from app.pipelines.ingestion.offline_embedder import OfflineEmbedderPipeline

# Dynamic defaults from .env via app settings
try:
    from core.config import get_settings

    _s = get_settings()
    DEFAULT_QDRANT_URL = _s.qdrant.url or f"http://{_s.qdrant.host}:{_s.qdrant.port}"
    DEFAULT_QDRANT_API_KEY = _s.qdrant.api_key.get_secret_value() if _s.qdrant.api_key else None
    DEFAULT_MINIO_ENDPOINT = _s.minio.endpoint
    DEFAULT_MINIO_ACCESS_KEY = _s.minio.access_key.get_secret_value()
    DEFAULT_MINIO_SECRET_KEY = _s.minio.secret_key.get_secret_value()
    DEFAULT_COLLECTION = _s.qdrant.collection
    DEFAULT_RAW_BUCKET = _s.minio.raw_bucket
    DEFAULT_DERIVED_BUCKET = _s.minio.derived_bucket
except Exception:
    DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6335")
    DEFAULT_QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    DEFAULT_MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9003")
    DEFAULT_MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    DEFAULT_MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "scenes")
    DEFAULT_RAW_BUCKET = os.getenv("MINIO_RAW_BUCKET", "scenesearch-raw")
    DEFAULT_DERIVED_BUCKET = os.getenv("MINIO_DERIVED_BUCKET", "scenesearch-derived")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jsonl",
        type=str,
        default=os.getenv(
            "CAPTIONS_JSONL",
            "/home/sysadmin/vin/SceneSearch/cache_qwen_captions.jsonl",
        ),
        help="Path to JSONL file containing frame captions and metadata",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=DEFAULT_QDRANT_URL,
        help=f"Qdrant service URL (default: {DEFAULT_QDRANT_URL})",
    )
    parser.add_argument(
        "--qdrant-api-key",
        type=str,
        default=DEFAULT_QDRANT_API_KEY,
        help="Qdrant API key",
    )
    parser.add_argument(
        "--minio-endpoint",
        type=str,
        default=DEFAULT_MINIO_ENDPOINT,
        help=f"MinIO service endpoint (default: {DEFAULT_MINIO_ENDPOINT})",
    )
    parser.add_argument(
        "--minio-access-key",
        type=str,
        default=DEFAULT_MINIO_ACCESS_KEY,
        help=f"MinIO access key (default: {DEFAULT_MINIO_ACCESS_KEY})",
    )
    parser.add_argument(
        "--minio-secret-key",
        type=str,
        default=DEFAULT_MINIO_SECRET_KEY,
        help=f"MinIO secret key (default: {DEFAULT_MINIO_SECRET_KEY})",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=DEFAULT_COLLECTION,
        help=f"Qdrant collection name (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--raw-bucket",
        type=str,
        default=DEFAULT_RAW_BUCKET,
        help=f"MinIO bucket for raw video files (default: {DEFAULT_RAW_BUCKET})",
    )
    parser.add_argument(
        "--derived-bucket",
        type=str,
        default=DEFAULT_DERIVED_BUCKET,
        help=f"MinIO bucket for frame image files (default: {DEFAULT_DERIVED_BUCKET})",
    )
    parser.add_argument(
        "--qwen-model",
        type=str,
        default=os.getenv("QWEN_MODEL", "Qwen/Qwen3-VL-Embedding-2B"),
        help="Qwen embedding model name (default: Qwen/Qwen3-VL-Embedding-2B)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("BATCH_SIZE", "64")),
        help="Batch size for model inference and Qdrant indexing (default: 64)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to process (useful for dry runs / testing)",
    )
    parser.add_argument(
        "--skip-minio",
        action="store_true",
        help="Skip uploading raw video and frame image assets to MinIO",
    )

    args = parser.parse_args()

    pipeline = OfflineEmbedderPipeline(
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        minio_endpoint=args.minio_endpoint,
        minio_access_key=args.minio_access_key,
        minio_secret_key=args.minio_secret_key,
        collection_name=args.collection,
        raw_bucket=args.raw_bucket,
        derived_bucket=args.derived_bucket,
        batch_size=args.batch_size,
        qwen_model_name=args.qwen_model,
    )

    total = pipeline.process_jsonl_file(
        jsonl_path=args.jsonl,
        limit=args.limit,
        skip_minio=args.skip_minio,
    )

    print(f"\nProcessing complete! Successfully indexed {total} records into Qdrant & MinIO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
