"""Metadata stage with Vision-Language Model (VLM) scene captioning & structured attributes."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import httpx
from loguru import logger
from PIL import Image

from core.config import Settings, get_settings
from core.ingestion import SEQUENCE_METADATA_PROMPT_VERSION
from pipelines.common.metadata import VLMSequenceResult, unknown_metadata
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.scene_metadata import aggregate_observations, observation_from_frame

VLM_METADATA_PROMPT = """Analyze the supplied chronological, privacy-processed dashcam images.
Return one JSON object containing a caption for the chunk, observations for EACH
supplied frame, and temporal_observations. Copy frame_index and absolute timestamp_ms
exactly from the input. Describe only what the supplied images support.
Keep objects, attributes, and concept evidence scoped to their individual frames.
Use singular object class names, e.g. car, truck, bus, person, motorcycle, bicycle.
Only put explicitly observed positive counts in object_counts; use null or omit
the count when unknown. Do not infer counts from traffic density or object presence.
Uncertain concepts belong in unknown_concepts, not absent_concepts. Not seeing an
object in selected frames does not prove absence throughout the chunk.
Use unknown/null for uncertain attributes. Never combine an object in one image
with an attribute of another object in another image.
Temporal descriptions are VLM inferences, NOT tracking evidence. Each must cite at
least two supplied frame_indices with their exact timestamps_ms in chronological
order. With only one image return no temporal_observations. Do not fabricate tracks,
speeds, trajectories, or observations between the supplied timestamps.
Return ONLY valid JSON matching this schema, without markdown:
""" + json.dumps(VLMSequenceResult.model_json_schema(), sort_keys=True)


@dataclass
class VLMRequestCache:
    """Job-local cache of validated responses to identical sequence requests."""

    responses: dict[str, VLMSequenceResult] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)


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
    with image.convert("RGB") as img, io.BytesIO() as buf:
        img.thumbnail((max_edge, max_edge), Image.Resampling.BILINEAR)
        img.save(buf, format="JPEG", quality=80, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _fallback_metadata(
    objects: list[str], time_sec: float, *, status: str = "failed", reason: str = "vlm_unavailable"
) -> dict[str, Any]:
    return unknown_metadata(
        objects, status=status, reason=reason, timestamp_ms=round(time_sec * 1000)
    )


def _sequence_metadata(
    scene: SceneRecord,
    selected: list[FrameRecord],
    result: VLMSequenceResult | None,
    *,
    status: str = "failed",
    reason: str = "vlm_unavailable",
    model: str | None = None,
) -> dict[str, Any]:
    references = {frame.frame_index: frame.timestamp_ms for frame in selected}
    returned = (
        {observation.frame_index: observation for observation in result.observations}
        if result
        else {}
    )
    if any(
        references.get(index) != observation.timestamp_ms for index, observation in returned.items()
    ):
        raise ValueError("VLM returned an observation outside the supplied frame references")
    observations = []
    for frame in selected:
        observation = returned.get(frame.frame_index)
        data = (
            observation.model_dump(exclude={"frame_index", "timestamp_ms"})
            if observation
            else _fallback_metadata(
                [d.class_name for d in frame.detections],
                frame.timestamp_ms / 1000,
                status=status,
                reason="observation_missing" if result else reason,
            )
        )
        if observation is not None:
            data["enrichment"] = {
                "status": "success",
                "source": "vlm_sequence",
                "model": model,
                "timestamp_ms": frame.timestamp_ms,
                "prompt_version": SEQUENCE_METADATA_PROMPT_VERSION,
            }
        observations.append(observation_from_frame(replace(frame, metadata={"vlm_data": data})))
    representative = scene.representative_frame or selected[0]
    complete = all(observation.status == "success" for observation in observations)
    return aggregate_observations(
        observations,
        sampled_count=scene.metadata.get("sampled_frame_count"),
        representative_frame_index=representative.frame_index,
        representative_timestamp_ms=representative.timestamp_ms,
        sequence_caption=result.caption if result and complete else None,
        temporal_observations=result.temporal_observations if result else None,
    )


def _sequence_payload(
    scene: SceneRecord, selected: list[FrameRecord], settings: Settings
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "video_id": scene.video_id,
                    "start_ms": scene.start_ms,
                    "end_ms": scene.end_ms,
                    "interval": "instant"
                    if scene.start_ms == scene.end_ms
                    else "[start_ms, end_ms)",
                    "prompt_version": SEQUENCE_METADATA_PROMPT_VERSION,
                },
                sort_keys=True,
            ),
        }
    ]
    for frame in selected:
        if frame.display_image is None:
            raise ValueError("VLM request requires a privacy derivative")
        content.append(
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "frame_index": frame.frame_index,
                        "timestamp_ms": frame.timestamp_ms,
                        "offset_ms": frame.timestamp_ms - scene.start_ms,
                    },
                    sort_keys=True,
                ),
            }
        )
        content.append(
            {"type": "image_url", "image_url": {"url": _image_to_data_url(frame.display_image)}}
        )
    return {
        "model": settings.llm.model,
        "messages": [
            {"role": "system", "content": VLM_METADATA_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.1,
        "max_tokens": settings.video.vlm_max_tokens,
        # Nemotron 3.5 Super VL can spend its token budget on reasoning and
        # return null `message.content` unless thinking is explicitly disabled.
        "chat_template_kwargs": {"enable_thinking": False},
    }


async def _extract_scene_vlm(
    scene: SceneRecord,
    selected: list[FrameRecord],
    *,
    client: httpx.AsyncClient | None,
    settings: Settings,
    semaphore: asyncio.Semaphore,
    cache: VLMRequestCache,
) -> None:
    scene.metadata["vlm_request_count"] = 0
    if any(frame.privacy_status != "verified" or frame.display_image is None for frame in selected):
        scene.metadata["vlm_data"] = _sequence_metadata(
            scene, selected, None, reason="privacy_not_verified"
        )
        return
    api_key = settings.llm.api_key
    if client is None or api_key is None:
        scene.metadata["vlm_data"] = _sequence_metadata(
            scene, selected, None, status="not_configured", reason="api_key_missing"
        )
        return
    payload = _sequence_payload(scene, selected, settings)
    url = f"{str(settings.llm.base_url).rstrip('/')}/chat/completions"
    fingerprint = hashlib.sha256(
        json.dumps({"url": url, "payload": payload}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    async with cache.locks.setdefault(fingerprint, asyncio.Lock()):
        cached = cache.responses.get(fingerprint)
        if cached is not None:
            scene.metadata["vlm_data"] = _sequence_metadata(
                scene, selected, cached, model=settings.llm.model
            )
            return
        async with semaphore:
            for attempt in range(settings.video.vlm_attempts_per_request):
                try:
                    scene.metadata["vlm_request_count"] += 1
                    response = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {api_key.get_secret_value()}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if response.status_code == 429:
                        await asyncio.sleep(1 + attempt)
                        continue
                    response.raise_for_status()
                    choices = response.json().get("choices") or []
                    text = (choices[0].get("message") or {}).get("content") if choices else None
                    parsed = _parse_json_dict(text or "")
                    if parsed is None:
                        raise ValueError("VLM returned no JSON sequence response")
                    result = VLMSequenceResult.model_validate(parsed)
                    data = _sequence_metadata(scene, selected, result, model=settings.llm.model)
                    scene.metadata["vlm_data"] = data
                    cache.responses[fingerprint] = result
                    return
                except Exception as exc:
                    logger.warning(
                        "VLM sequence failed for chunk {} (attempt {}): {}",
                        scene.scene_id,
                        attempt + 1,
                        exc,
                    )
                    if attempt + 1 < settings.video.vlm_attempts_per_request:
                        await asyncio.sleep(0.5)
    scene.metadata["vlm_data"] = _sequence_metadata(scene, selected, None)


async def extract_scene_vlm_metadata(
    scenes: Sequence[SceneRecord],
    max_concurrency: int | None = None,
    *,
    settings: Settings | None = None,
    request_cache: VLMRequestCache | None = None,
) -> None:
    """Analyze each chunk as one timestamped image sequence with scoped evidence."""
    settings = settings or get_settings()
    video = settings.video
    llm = settings.llm
    selections = []
    for scene in scenes:
        selected = scene.vlm_candidates or [scene.representative_frame or scene.keyframes[0]]
        if len(selected) > video.vlm_max_frames or len({f.frame_index for f in selected}) != len(
            selected
        ):
            raise ValueError("Invalid VLM candidate selection")
        selected = sorted(selected, key=lambda frame: (frame.timestamp_ms, frame.frame_index))
        if any(
            right.timestamp_ms <= left.timestamp_ms for left, right in zip(selected, selected[1:])
        ):
            raise ValueError("VLM candidates must have strictly increasing timestamps")
        if scene.representative_frame is not None and not any(
            frame.frame_index == scene.representative_frame.frame_index
            and frame.timestamp_ms == scene.representative_frame.timestamp_ms
            for frame in selected
        ):
            raise ValueError("VLM selection must include the representative reference")
        instant = len(selected) == 1 and scene.start_ms == scene.end_ms == selected[0].timestamp_ms
        if not instant and any(
            not scene.start_ms <= frame.timestamp_ms < scene.end_ms for frame in selected
        ):
            raise ValueError("VLM candidate timestamp is outside the chunk")
        selections.append((scene, selected))
    semaphore = asyncio.Semaphore(max_concurrency or video.vlm_concurrency)
    cache = request_cache if request_cache is not None else VLMRequestCache()

    async def analyze(client):
        await asyncio.gather(
            *(
                _extract_scene_vlm(
                    scene,
                    selected,
                    client=client,
                    settings=settings,
                    semaphore=semaphore,
                    cache=cache,
                )
                for scene, selected in selections
            )
        )

    if llm.api_key and llm.api_key.get_secret_value():
        async with httpx.AsyncClient(timeout=video.vlm_timeout_s) as client:
            await analyze(client)
    else:
        await analyze(None)


def extract_metadata(frames: Iterable[FrameRecord]) -> Iterator[FrameRecord]:
    for frame in frames:
        frame.metadata.setdefault("timestamp", {"value_ms": frame.timestamp_ms, "source": "media"})
        yield frame


__all__ = ["extract_metadata", "extract_scene_vlm_metadata"]
