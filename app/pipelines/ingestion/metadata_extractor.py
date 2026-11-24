"""Metadata stage with Vision-Language Model (VLM) scene captioning & structured attributes."""

from __future__ import annotations

import asyncio
import base64
import io
import json
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import httpx
from loguru import logger
from PIL import Image

from core.config import Settings, get_settings
from pipelines.common.metadata import VLMResult, unknown_metadata
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.scene_metadata import aggregate_scene_metadata

VLM_METADATA_PROMPT = """You are an expert autonomous driving visual perception AI.
Given a driving scene / dashcam image, extract detailed structured metadata strictly as valid JSON matching this schema:
{
  "metadata": {
    "scene": {
      "scene_type": "residential|urban|highway|rural|tunnel|parking|unknown",
      "road_type": "residential|city_street|highway|country_road|unknown",
      "weather": "clear|rainy|foggy|overcast|snowy|unknown",
      "time_of_day": "day|night|dusk|dawn|unknown",
      "lighting": "daylight|artificial|dim|dark|unknown",
      "road_surface": "dry|wet|snowy|muddy|unknown",
      "visibility": "high|good|medium|low|unknown",
      "traffic_density": "empty|low|medium|heavy|unknown"
    },
    "traffic": {
      "cars": "none|low|medium|high",
      "motorcycles": "none|low|medium|high",
      "trucks": "none|low|medium|high",
      "buses": "none|low|medium|high",
      "pedestrians": "none|low|medium|high"
    },
    "traffic_control": {
      "traffic_light": {
        "present": false,
        "state": "unknown|red|green|yellow"
      },
      "signs": []
    },
    "road": {
      "lane_count": null,
      "ego_lane": "unknown|left|center|right",
      "lane_marking": "none|solid|dashed|unknown",
      "intersection": false,
      "roundabout": false,
      "curve": "straight|left|right|unknown",
      "road_markings": []
    },
    "ocr": [],
    "retrieval_tags": ["tag1", "tag2"],
    "caption": "Detailed visual description of the dashcam frame."
  },
  "present_concepts": ["concept1", "concept2"],
  "absent_concepts": ["concept3"]
}
Return ONLY valid JSON, no markdown."""


def _parse_json_dict(text: str) -> dict[str, Any] | None:
    """Robustly parse JSON object from LLM response text with markdown/extra text handling."""
    if not text:
        return None
    cleaned = text.strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    if "```" in cleaned:
        for block in cleaned.split("```"):
            candidate = block.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    start_idx = cleaned.find("{")
    while start_idx != -1:
        depth = 0
        for i in range(start_idx, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(cleaned[start_idx : i + 1])
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass
                    break
        start_idx = cleaned.find("{", start_idx + 1)

    return None


def _image_to_data_url(image: Image.Image, max_edge: int = 480) -> str:
    img = image.convert("RGB")
    img.thumbnail((max_edge, max_edge), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _fallback_metadata(
    objects: list[str], time_sec: float, *, status: str = "failed", reason: str = "vlm_unavailable"
) -> dict[str, Any]:
    return unknown_metadata(
        objects, status=status, reason=reason, timestamp_ms=round(time_sec * 1000)
    )


async def _extract_frame_vlm(
    frame: FrameRecord,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    models_to_try: list[str],
    semaphore: asyncio.Semaphore,
    attempts_per_frame: int = 2,
) -> None:
    time_sec = frame.timestamp_ms / 1000.0
    objects = [d.class_name for d in frame.detections] if frame.detections else []

    if frame.display_image is None or frame.privacy_status != "verified":
        frame.metadata["vlm_data"] = _fallback_metadata(objects, time_sec)
        return

    data_url = _image_to_data_url(frame.display_image)
    payload = {
        "messages": [
            {"role": "system", "content": VLM_METADATA_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this driving dashcam frame and output JSON metadata.",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1500,
        # Nemotron 3.5 Super VL can spend its token budget on reasoning and
        # return null `message.content` unless thinking is explicitly disabled.
        "chat_template_kwargs": {"enable_thinking": False},
    }

    async with semaphore:
        for model_name in models_to_try:
            for attempt in range(attempts_per_frame):
                try:
                    payload["model"] = model_name
                    frame.metadata["vlm_request_count"] = (
                        frame.metadata.get("vlm_request_count", 0) + 1
                    )
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code == 429:
                        await asyncio.sleep(1.0 + attempt * 1.0)
                        continue
                    if response.status_code != 200:
                        logger.warning(
                            "VLM model {} returned HTTP {}: {}",
                            model_name,
                            response.status_code,
                            response.text[:300],
                        )
                        continue
                    choices = response.json().get("choices")
                    if not choices:
                        logger.warning(
                            "VLM model {} returned no choices: {}",
                            model_name,
                            response.text[:300],
                        )
                        continue
                    message = choices[0].get("message") or {}
                    content = message.get("content") or ""
                    if not content and message.get("reasoning_content"):
                        logger.warning(
                            "VLM model {} returned reasoning without content", model_name
                        )
                        continue
                    parsed = _parse_json_dict(content)
                    if parsed and "metadata" in parsed and "caption" in parsed["metadata"]:
                        result = VLMResult.model_validate(parsed).model_dump()
                        result["enrichment"] = {
                            "status": "success",
                            "source": "vlm",
                            "model": model_name,
                            "timestamp_ms": frame.timestamp_ms,
                        }
                        frame.metadata["vlm_data"] = result
                        return
                except Exception as exc:
                    logger.debug("VLM model {} failed on frame: {}", model_name, exc)
                    await asyncio.sleep(0.5)
                    continue

    # Graceful fallback if VLM fails or is unavailable
    frame.metadata["vlm_data"] = _fallback_metadata(objects, time_sec)


async def extract_scene_vlm_metadata(
    scenes: Sequence[SceneRecord],
    max_concurrency: int | None = None,
    *,
    settings: Settings | None = None,
) -> None:
    """Analyze only selected verified derivatives, then aggregate per-frame evidence."""
    settings = settings or get_settings()
    video = settings.video
    llm = settings.llm
    frames = []
    for scene in scenes:
        selected = scene.vlm_candidates or [scene.representative_frame or scene.keyframes[0]]
        if len(selected) > video.vlm_max_frames or len({f.frame_index for f in selected}) != len(
            selected
        ):
            raise ValueError("Invalid VLM candidate selection")
        frames.extend(selected)
    if not llm.api_key:
        for frame in frames:
            frame.metadata["vlm_data"] = _fallback_metadata(
                [d.class_name for d in frame.detections],
                frame.timestamp_ms / 1000.0,
                status="not_configured",
                reason="api_key_missing",
            )
    else:
        api_key = llm.api_key.get_secret_value()
        url = f"{str(llm.base_url).rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        semaphore = asyncio.Semaphore(max_concurrency or video.vlm_concurrency)
        async with httpx.AsyncClient(timeout=video.vlm_timeout_s) as client:
            await asyncio.gather(
                *(
                    _extract_frame_vlm(
                        frame,
                        client,
                        url,
                        headers,
                        [llm.model],
                        semaphore,
                        video.vlm_attempts_per_frame,
                    )
                    for frame in frames
                )
            )
    for scene in scenes:
        aggregate_scene_metadata(scene)


def extract_metadata(frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]:
    for frame in frames:
        frame.metadata.setdefault("timestamp", {"value_ms": frame.timestamp_ms, "source": "media"})
        yield frame


__all__ = ["extract_metadata", "extract_scene_vlm_metadata"]
