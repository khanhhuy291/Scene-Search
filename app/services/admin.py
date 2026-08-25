"""Live admin telemetry: index coverage, Qdrant, MinIO, and Celery."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from loguru import logger

from core.config import get_settings
from infrastructure.minio import get_derived_storage, get_minio_storage, get_raw_storage
from infrastructure.qdrant import get_qdrant_client
from repositories.task_status import list_task_statuses
from schemas.admin import (
    AdminTelemetry,
    BucketUsage,
    CorpusHealth,
    EvalReportResponse,
    LabelCount,
    QdrantHealth,
    RecentJob,
    StorageHealth,
    VectorSummary,
    WorkerHealth,
    WorkerNode,
)
from search.catalog import get_catalog


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _pct(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return round(100 * part / whole)


def _label_counts(values: list[str | None], *, limit: int = 12) -> list[LabelCount]:
    counts: Counter[str] = Counter()
    for value in values:
        if not value:
            continue
        counts[value.strip().lower()] += 1
    return [LabelCount(name=name, count=count) for name, count in counts.most_common(limit)]


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.hostname:
        return url
    user = parts.username or ""
    host = parts.hostname
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{user}:***@{host}{port}" if user else f"{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _vector_summaries(vectors: object) -> list[VectorSummary]:
    if vectors is None:
        return []
    if isinstance(vectors, dict):
        rows: list[VectorSummary] = []
        for name, params in vectors.items():
            distance = getattr(params, "distance", "")
            rows.append(
                VectorSummary(
                    name=str(name),
                    size=getattr(params, "size", None),
                    distance=str(distance) if distance else "",
                )
            )
        return rows
    distance = getattr(vectors, "distance", "")
    return [
        VectorSummary(
            name="",
            size=getattr(vectors, "size", None),
            distance=str(distance) if distance else "",
        )
    ]


async def _corpus_health() -> CorpusHealth:
    settings = get_settings()
    catalog = get_catalog()
    caption_vector = settings.search.caption_vector.strip()
    try:
        await catalog.ensure_loaded(get_qdrant_client())
    except Exception as exc:
        logger.warning("Catalog load failed for admin telemetry: {error}", error=exc)
        return CorpusHealth(
            caption_tower_installed=bool(caption_vector),
            caption_tower_name=caption_vector,
        )

    frames = catalog.frames
    total = len(frames)
    with_media = sum(1 for frame in frames if frame.has_thumbnail)
    with_caption = sum(1 for frame in frames if frame.caption.strip())
    return CorpusHealth(
        videos=catalog.video_count,
        keyframes=total,
        media_coverage_pct=_pct(with_media, total),
        caption_coverage_pct=_pct(with_caption, total),
        embedding_coverage_pct=100 if total else 0,
        caption_tower_installed=bool(caption_vector),
        caption_tower_name=caption_vector,
        labels={
            "weather": _label_counts([frame.weather for frame in frames]),
            "time_of_day": _label_counts([frame.time_of_day for frame in frames]),
            "scene": _label_counts([frame.road_condition for frame in frames]),
        },
    )


async def _qdrant_health() -> QdrantHealth:
    settings = get_settings().qdrant
    health = QdrantHealth(collection=settings.collection)
    try:
        client = get_qdrant_client()
        info = await client.get_collection(settings.collection)
        vectors = getattr(getattr(info.config, "params", None), "vectors", None)
        hnsw = getattr(info.config, "hnsw_config", None)
        health.reachable = True
        health.points_count = getattr(info, "points_count", None)
        health.vectors = _vector_summaries(vectors)
        health.hnsw_m = getattr(hnsw, "m", None)
        health.ef_construct = getattr(hnsw, "ef_construct", None)
    except Exception as exc:
        logger.warning("Qdrant telemetry failed: {error}", error=exc)
        health.detail = str(exc)
    return health


def _bucket_usage(name: str, lister: Any) -> BucketUsage:
    try:
        count = 0
        total_bytes = 0
        for obj in lister:
            count += 1
            total_bytes += int(getattr(obj, "size", 0) or 0)
            if count >= 200_000:
                break
        return BucketUsage(name=name, objects=count, bytes=total_bytes)
    except Exception as exc:
        return BucketUsage(name=name, detail=str(exc))


def _storage_health() -> StorageHealth:
    settings = get_settings().minio
    buckets: list[BucketUsage] = []
    try:
        seen: set[str] = set()
        for storage in (get_minio_storage(), get_raw_storage(), get_derived_storage()):
            if storage.bucket in seen:
                continue
            seen.add(storage.bucket)
            buckets.append(
                _bucket_usage(
                    storage.bucket,
                    storage.client.list_objects(storage.bucket, recursive=True),
                )
            )

        if settings.scene_media_endpoint and settings.scene_media_bucket not in seen:
            from api.v1.media import get_media_store

            store = get_media_store()
            list_objects = getattr(store, "list_objects", None)
            if callable(list_objects):
                buckets.append(
                    _bucket_usage(
                        settings.scene_media_bucket,
                        list_objects(settings.scene_media_bucket, recursive=True),
                    )
                )
            else:
                buckets.append(
                    BucketUsage(
                        name=settings.scene_media_bucket,
                        detail="Object listing is not available on the console media store",
                    )
                )
        reachable = any(row.objects is not None for row in buckets)
        return StorageHealth(reachable=reachable, buckets=buckets)
    except Exception as exc:
        logger.warning("Storage telemetry failed: {error}", error=exc)
        return StorageHealth(reachable=False, buckets=buckets, detail=str(exc))


def _processed_count(stats: dict[str, Any] | None) -> int | None:
    total = (stats or {}).get("total")
    if isinstance(total, dict):
        return int(sum(int(value) for value in total.values()))
    if isinstance(total, int):
        return total
    return None


def _worker_health() -> WorkerHealth:
    settings = get_settings().celery
    health = WorkerHealth(broker=_redact_url(settings.broker_url))
    try:
        from worker.celery_app import celery_app

        inspect = celery_app.control.inspect(timeout=1.0)
        stats = inspect.stats() or {}
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        workers: list[WorkerNode] = []
        in_flight = 0
        for name, node_stats in stats.items():
            pool = (node_stats or {}).get("pool") or {}
            running = active.get(name) or []
            waiting = reserved.get(name) or []
            in_flight += len(running) + len(waiting)
            workers.append(
                WorkerNode(
                    id=name,
                    status="BUSY" if running else "IDLE",
                    concurrency_max=pool.get("max-concurrency"),
                    active_count=len(running),
                    reserved_count=len(waiting),
                    active_tasks=[
                        f"{task.get('name', 'task')} #{str(task.get('id', ''))[:8]}"
                        for task in running[:6]
                    ],
                    processed=_processed_count(node_stats),
                )
            )
        health.reachable = True
        health.workers = workers
        health.worker_count = len(workers)
        health.queue_depth = in_flight
        if not workers:
            health.detail = "Broker reachable; no Celery workers answered inspect"
    except Exception as exc:
        logger.warning("Celery telemetry failed: {error}", error=exc)
        health.detail = str(exc)
    return health


async def collect_telemetry() -> AdminTelemetry:
    corpus = await _corpus_health()
    qdrant = await _qdrant_health()
    storage = await asyncio.to_thread(_storage_health)
    workers = await asyncio.to_thread(_worker_health)
    try:
        jobs, total = await list_task_statuses(limit=12, offset=0)
    except Exception as exc:
        logger.warning("Ingestion job list failed: {error}", error=exc)
        jobs, total = [], 0

    recent = [
        RecentJob(
            task_id=job.task_id,
            video_path=job.video_path,
            status=job.status.value if hasattr(job.status, "value") else str(job.status),
            progress=job.progress,
            updated_at=job.updated_at.isoformat() if job.updated_at else None,
            error=job.error,
        )
        for job in jobs
    ]
    return AdminTelemetry(
        generated_at=_utc_now(),
        corpus=corpus,
        qdrant=qdrant,
        storage=storage,
        workers=workers,
        recent_jobs=recent,
        job_total=total,
    )


def _eval_candidates() -> list[Path]:
    app_dir = Path(__file__).resolve().parents[1]
    repo = app_dir.parent
    return [
        repo / "reports" / "eval.json",
        app_dir / "eval" / "baselines" / "live.json",
    ]


def load_eval_report() -> EvalReportResponse:
    for path in _eval_candidates():
        if not path.is_file() or path.stat().st_size < 8:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return EvalReportResponse(available=False, path=str(path), detail=str(exc))
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
        return EvalReportResponse(
            available=True,
            path=str(path),
            generated_at=mtime,
            report=payload if isinstance(payload, dict) else {"value": payload},
        )
    return EvalReportResponse(
        available=False,
        detail="No eval report on disk. Run `make eval mot=... out=../reports/eval`.",
    )
