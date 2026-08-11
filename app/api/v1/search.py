"""Semantic scene search and video streaming API endpoints."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from search.hybrid import HybridQdrantSearchEngine

router = APIRouter(prefix="", tags=["search"])

_search_engine: HybridQdrantSearchEngine | None = None


def get_search_engine() -> HybridQdrantSearchEngine:
    global _search_engine
    if _search_engine is None:
        _search_engine = HybridQdrantSearchEngine()
    return _search_engine


class SearchApiRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=12, ge=1, le=100)
    alpha_visual: float = Field(default=0.5, ge=0.0, le=1.0)
    alpha_text: float = Field(default=0.5, ge=0.0, le=1.0)
    video_id: str | None = None


def _format_timestamp(seconds: float) -> str:
    start_sec = max(0, int(seconds))
    end_sec = start_sec + 5
    m1, s1 = divmod(start_sec, 60)
    m2, s2 = divmod(end_sec, 60)
    return f"{m1:02d}:{s1:02d} - {m2:02d}:{s2:02d}"


def _extract_title(caption: str, video_id: str) -> str:
    if not caption:
        return f"Scene in {video_id}"
    sentences = re.split(r"[.!?]", caption)
    first_sent = sentences[0].strip()
    if len(first_sent) > 80:
        return first_sent[:77] + "..."
    return first_sent or f"Scene in {video_id}"


def _extract_tags(caption: str) -> list[str]:
    common_words = {
        "this", "is", "a", "an", "the", "view", "from", "in", "on", "of", "and",
        "with", "to", "for", "at", "by", "scene", "video", "dashcam", "camera",
        "looking", "captured", "driving", "street", "road"
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", caption.lower())
    filtered = [w for w in words if w not in common_words]
    unique_tags: list[str] = []
    for w in filtered:
        if w not in unique_tags:
            unique_tags.append(w)
        if len(unique_tags) >= 5:
            break
    return unique_tags or ["video", "scene"]


@router.post("/search")
async def search_scenes_post(payload: SearchApiRequest) -> dict[str, Any]:
    return await _execute_search(
        query=payload.query,
        limit=payload.limit,
        alpha_visual=payload.alpha_visual,
        alpha_text=payload.alpha_text,
    )


@router.get("/search")
async def search_scenes_get(
    query: str = Query(..., min_length=1),
    limit: int = Query(12, ge=1, le=100),
    alpha_visual: float = Query(0.5, ge=0.0, le=1.0),
    alpha_text: float = Query(0.5, ge=0.0, le=1.0),
) -> dict[str, Any]:
    return await _execute_search(
        query=query,
        limit=limit,
        alpha_visual=alpha_visual,
        alpha_text=alpha_text,
    )


async def _execute_search(
    query: str,
    limit: int,
    alpha_visual: float,
    alpha_text: float,
) -> dict[str, Any]:
    engine = get_search_engine()
    raw_results = await engine.search(
        query_text=query,
        top_k=limit,
        alpha_visual=alpha_visual,
        alpha_text=alpha_text,
    )

    formatted_scenes: list[dict[str, Any]] = []
    for item in raw_results:
        caption = item.get("qwen_caption", "")
        sec = float(item.get("timestamp_sec", 0.0))
        vid = item.get("video_id", "")
        vpath = item.get("video_path", "")

        # Score calculation in hybrid.py is RRF raw score * 100
        # Convert RRF score (around 0.01-0.03) or normalized score to display percentage (70-98%)
        raw_score = float(item.get("score", 0.0))
        # RRF formula gives values around 1/60 ~ 0.016. If multiplied by 100 in hybrid.py, raw_score is ~ 0.8 - 2.5
        display_score = round(min(99.9, max(65.0, raw_score * 45.0 + 45.0)), 1)

        minio_kf_key = item.get("minio_keyframe_key") or item.get("minio_thumbnail_key") or ""
        thumbnail_url = (
            f"/api/v1/assets/thumbnail?video_id={vid}&timestamp_sec={sec}&key={minio_kf_key}"
        )

        formatted_scenes.append(
            {
                "id": item.get("id"),
                "video_id": vid,
                "videoName": Path(vpath).name if vpath else f"{vid}.mov",
                "video_path": vpath,
                "title": _extract_title(caption, vid),
                "description": caption,
                "timestamp": _format_timestamp(sec),
                "timestamp_sec": sec,
                "frame_no": item.get("frame_no", -1),
                "score": display_score,
                "visual_score": round(item.get("visual_score", 0.0), 4),
                "text_score": round(item.get("text_score", 0.0), 4),
                "tags": _extract_tags(caption),
                "thumbnail": thumbnail_url,
                "video_url": f"/api/v1/videos/stream?video_id={vid}#t={sec}",
            }
        )

    return {
        "query": query,
        "results": formatted_scenes,
        "total": len(formatted_scenes),
    }


@router.get("/assets/thumbnail")
async def stream_thumbnail(
    key: str | None = Query(None),
    video_id: str | None = Query(None),
    timestamp_sec: float = Query(0.0),
) -> Response:
    from fastapi.responses import Response
    from infrastructure.minio import get_minio_storage

    # 1. Try fetching from MinIO if key is provided
    if key and key.strip():
        storage = get_minio_storage()
        try:
            res = storage.client.get_object(storage.bucket, key.strip())
            data = res.read()
            res.close()
            res.release_conn()
            return Response(
                content=data,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        except Exception:
            pass

    # 2. Dynamic keyframe extraction from video on disk via OpenCV
    if video_id and video_id.strip():
        video_dir = Path("/home/sysadmin/vin/videos/videos/train")
        matches = list(video_dir.glob(f"{video_id.strip()}.*"))
        if matches:
            target_path = matches[0]
            import cv2
            cap = cv2.VideoCapture(str(target_path))
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                frame_index = int(timestamp_sec * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    ret_jpg, jpeg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret_jpg:
                        return Response(
                            content=jpeg_buf.tobytes(),
                            media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=86400"},
                        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Thumbnail asset not found for key '{key}' or video_id '{video_id}'",
    )


@router.get("/videos/stream")
async def stream_video(video_id: str = Query(...)) -> FileResponse:
    # Resolve video path
    video_dir = Path("/home/sysadmin/vin/videos/videos/train")
    target_path = video_dir / f"{video_id}.mov"

    if not target_path.exists():
        # Check alternative extensions or paths
        matches = list(video_dir.glob(f"{video_id}.*"))
        if matches:
            target_path = matches[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video file for '{video_id}' not found on server",
            )

    return FileResponse(
        path=target_path,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/admin/stats")
async def get_admin_stats() -> dict[str, Any]:
    from infrastructure.qdrant import get_qdrant_client
    from core.config import get_settings
    client = get_qdrant_client()
    settings = get_settings().qdrant

    qdrant_points = 0
    qdrant_status = "ok"
    try:
        if await client.collection_exists(settings.collection):
            info = await client.get_collection(settings.collection)
            qdrant_points = info.points_count or 0
    except Exception as exc:
        qdrant_status = str(exc)

    return {
        "qdrant": {
            "collection": settings.collection,
            "points_count": qdrant_points,
            "status": qdrant_status,
            "vectors": ["siglip_visual (768d)", "bge_text (1024d)"],
        },
        "minio": {
            "bucket": "scenesearch",
            "status": "ok",
        },
        "system": {
            "status": "operational",
            "celery_queue": "ingestion",
        },
    }


