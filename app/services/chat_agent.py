"""Multimodal Conversational QA Agent with Iterative Paraphrasing and Visual Reflection."""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

import httpx
from loguru import logger
from PIL import Image

from core.config import get_settings
from ml.image_cache import get_image_cache
from schemas.chat import ChatRequest, ChatResponse, SceneSource
from search.engine import get_search_engine

FORMULATION_SYSTEM_PROMPT = """You are the search query planner for SceneSearch, an autonomous driving video retrieval system.

Analyze the user's conversation and extract the core visual scene query for dense vector retrieval.
Important rules:
1. Translate Vietnamese intent into natural English visual descriptors.
2. Handle colloquialisms and common Vietnamese typos:
   - "bãi đổ xe" or "bãi đỗ xe" -> "parking lot", "parking area", "parked cars" (never translate to scrapyard/junkyard/dump!).
   - "mở cửa xe" -> "person opening car door" or "person standing by vehicle door".
   - "vượt đèn đỏ" -> "car passing red light at intersection".
3. Strip conversational QA sub-questions (e.g. "Lúc đó người đó là nam hay nữ?", "xe màu gì?") from the vector search query, keeping only the core visual scene elements (e.g. "person opening car door in parking lot").

Output ONLY a raw JSON object (no markdown, no thinking tags, no extra text):
{
  "needs_search": boolean,
  "search_query": "clean, concise English visual search phrase for dense vector retrieval",
  "reason": "short explanation under 10 words"
}
"""

PARAPHRASE_SYSTEM_PROMPT = """You are an expert traffic, dashcam, and street video search query refiner.
A previous vector query returned insufficient or empty results from the video database.
Analyze why it may have failed and generate a broader, more effective visual search phrase in English.

Important:
- Always preserve traffic, road, street, or camera context (e.g. for "cat", generate "cat on road or street" or "small animal on roadside", NEVER isolated non-visual queries like "cat color").
- Broaden terms (e.g. "yellow bus" -> "transit bus or large public vehicle", "cat" -> "cat or small animal crossing street").

Output ONLY a JSON object:
{
  "search_query": "paraphrased broader visual search phrase",
  "reason": "why this query is more effective for visual matching"
}
"""

QA_SYSTEM_PROMPT = """You are SceneSearch Multimodal AI Assistant, an expert autonomous driving and traffic video analyst.
You possess native Vision-Language capabilities and can directly inspect forward dashcam and traffic camera keyframe images.

Guidelines:
1. Carefully observe the visual details in each provided keyframe image (vehicle types, colors, actions, pedestrians, lane markings, weather, lighting, traffic density).
2. Answer the user's specific question directly, accurately, and politely.
3. Explicitly cite the scenes using [Scene 1], [Scene 2], etc., matching the Video ID and timestamp.
4. If a detail requested by the user is not visible in the images, state so honestly.
5. Always respond in the same language as the user's inquiry (e.g. Vietnamese or English).
"""


class SceneSearchQAAgent:
    """Conversational Multimodal Agent that plans queries, iteratively refines searches, and inspects keyframe images."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def _call_vlm(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
        response_format: dict[str, str] | None = None,
    ) -> tuple[str, str | None]:
        """Send a request to NVIDIA NIM VLM with generous timeout and return (content, reasoning_content)."""
        llm = self._settings.llm
        if not llm.api_key:
            raise RuntimeError("LLM_API_KEY is not configured in environment.")

        api_key = llm.api_key.get_secret_value()
        url = f"{llm.base_url.rstrip('/')}/chat/completions"

        payload: dict[str, Any] = {
            "model": llm.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Generous 90s timeout with connection timeout to prevent ReadTimeout
        client_timeout = httpx.Timeout(90.0, connect=15.0, read=90.0, write=30.0)

        async with httpx.AsyncClient(timeout=client_timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(
                    "NVIDIA NIM VLM error {status}: {text}",
                    status=response.status_code,
                    text=response.text[:300],
                )
                raise RuntimeError(
                    f"VLM API returned error status {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return "", None

            message = choices[0].get("message", {})
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning_content") or choices[0].get("reasoning_content")
            return content.strip(), reasoning

    def _image_to_data_url(self, img: Image.Image, max_edge: int = 384, quality: int = 80) -> str:
        """Resize PIL Image and convert to compact base64 JPEG data URL (~25-35KB)."""
        w, h = img.size
        if max(w, h) > max_edge:
            scale = max_edge / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"

    async def _paraphrase_query(self, failed_query: str, user_original: str) -> str:
        """Ask LLM to reflect and generate an alternative visual search query."""
        messages = [
            {"role": "system", "content": PARAPHRASE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f'Original user request: "{user_original}"\nPrevious search query that returned low/zero matches: "{failed_query}"\nPlease generate an improved, broader, or synonymous visual search phrase.',
            },
        ]
        try:
            text, _ = await self._call_vlm(
                messages,
                temperature=0.3,
                max_tokens=250,
                response_format={"type": "json_object"},
            )
            cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                data = json.loads(match.group(0))
                return data.get("search_query", failed_query)
        except Exception as exc:
            logger.warning("Paraphrase generation failed: {}", exc)
        return failed_query

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Process chat message end-to-end with iterative query refinement and visual inspection."""
        engine = get_search_engine()
        image_cache = get_image_cache()

        # -------------------------------------------------------------
        # STEP 1: Initial Query Formulation & Intent Analysis
        # -------------------------------------------------------------
        formulation_messages: list[dict[str, Any]] = [
            {"role": "system", "content": FORMULATION_SYSTEM_PROMPT},
        ]
        for msg in request.history[-4:]:
            formulation_messages.append({"role": msg.role, "content": msg.content})
        formulation_messages.append({"role": "user", "content": request.message})

        try:
            formulation_text, _ = await self._call_vlm(
                formulation_messages,
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            cleaned = re.sub(r"<think>.*?</think>", "", formulation_text, flags=re.DOTALL).strip()
            match = re.search(r"\{[\s\S]*\}", cleaned)
            plan = (
                json.loads(match.group(0))
                if match
                else {"needs_search": True, "search_query": request.message}
            )
        except Exception as exc:
            logger.warning("Query formulation fallback: {}", exc)
            plan = {"needs_search": True, "search_query": request.message}

        needs_search = plan.get("needs_search", True)
        current_query = plan.get("search_query", request.message)

        # If general conversational greeting without search intent
        if not needs_search:
            general_messages = [
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                *[{"role": m.role, "content": m.content} for m in request.history[-6:]],
                {"role": "user", "content": request.message},
            ]
            content, reasoning = await self._call_vlm(general_messages, max_tokens=600)
            return ChatResponse(reply=content, reasoning=reasoning, sources=[], query_used=None)

        # -------------------------------------------------------------
        # STEP 2: Iterative Retrieval & Query Refinement Loop
        # -------------------------------------------------------------
        queries_tried: list[str] = [current_query]
        best_outcome = None
        max_iterations = 2

        for iteration in range(max_iterations):
            logger.info(
                "Chat Agent iteration {}/{} executing search for query: {!r}",
                iteration + 1,
                max_iterations,
                current_query,
            )
            outcome = await engine.search(
                query=current_query,
                limit=request.limit,
                mode="qwen",
                strict=False,
                rerank=False,
            )

            # If we found matches or this is the first result
            if outcome.matches and len(outcome.matches) > 0:
                best_outcome = outcome
                break
            else:
                best_outcome = outcome
                # If matches are empty and we still have iterations, reflect & paraphrase
                if iteration < max_iterations - 1:
                    refined = await self._paraphrase_query(current_query, request.message)
                    if refined and refined.strip() != current_query:
                        current_query = refined.strip()
                        queries_tried.append(current_query)

        final_outcome = best_outcome
        if not final_outcome or not final_outcome.matches:
            no_results_messages = [
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                *[{"role": m.role, "content": m.content} for m in request.history[-4:]],
                {
                    "role": "user",
                    "content": f"User question: {request.message}\n(System note: Vector search for queries {queries_tried} returned 0 matches in the database. Please kindly inform the user and suggest alternative search terms).",
                },
            ]
            content, reasoning = await self._call_vlm(no_results_messages, max_tokens=400)
            return ChatResponse(
                reply=content,
                reasoning=reasoning,
                sources=[],
                query_used=current_query,
                queries_tried=queries_tried,
                iterations=len(queries_tried),
            )

        # -------------------------------------------------------------
        # STEP 3: Visual Ingestion (Fetch Thumbnails from S3/Redis)
        # -------------------------------------------------------------
        items_to_fetch = []
        for match in final_outcome.matches:
            kf = match.keyframe
            frame_name = (
                kf.thumbnail_key.rsplit("/", 1)[-1]
                if kf.thumbnail_key
                else f"frame_{max(0, kf.frame_no):05d}.jpg"
            )
            items_to_fetch.append((str(kf.video_id or ""), frame_name))

        images = await image_cache.get_images_batch(items_to_fetch)

        # -------------------------------------------------------------
        # STEP 4: Multimodal Visual QA & Reasoning with Nemotron Omni VLM
        # -------------------------------------------------------------
        sources: list[SceneSource] = []
        user_content_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"User question: {request.message}\n\nI have retrieved {len(final_outcome.matches)} relevant candidate video scenes from the database using query '{current_query}':\n",
            }
        ]

        for idx, (match, img) in enumerate(zip(final_outcome.matches, images), start=1):
            kf = match.keyframe
            timecode = f"{int(kf.timestamp_s // 60):02d}:{int(kf.timestamp_s % 60):02d}"
            preview_url = f"/api/v1/media/thumbnail/{kf.point_id}" if kf.point_id else None
            clip_url = f"/api/v1/media/clip/{kf.point_id}" if kf.point_id else None

            sources.append(
                SceneSource(
                    video_id=kf.video_id,
                    frame_id=str(kf.frame_no),
                    point_id=kf.point_id,
                    timestamp=timecode,
                    timestamp_s=kf.timestamp_s,
                    caption=kf.caption,
                    preview_url=preview_url,
                    clip_url=clip_url,
                    score=float(match.score) if match.score is not None else None,
                )
            )

            scene_desc = (
                f"\n--- [Scene {idx}] ---\n"
                f"• Video ID: {kf.video_id}\n"
                f"• Timecode: {timecode} ({kf.timestamp_s:.1f}s)\n"
                f"• Caption: {kf.caption}\n"
                f"• Keyframe Image below:"
            )
            user_content_blocks.append({"type": "text", "text": scene_desc})

            if img is not None:
                data_url = self._image_to_data_url(img)
                user_content_blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    }
                )

        user_content_blocks.append(
            {
                "type": "text",
                "text": (
                    "\nPlease carefully analyze the images and metadata above, and answer the user's question with specific visual evidence, "
                    "citing each scene as [Scene 1], [Scene 2], etc."
                ),
            }
        )

        qa_messages: list[dict[str, Any]] = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
        ]
        for msg in request.history[-4:]:
            qa_messages.append({"role": msg.role, "content": msg.content})
        qa_messages.append({"role": "user", "content": user_content_blocks})

        reply, reasoning = await self._call_vlm(qa_messages, temperature=0.2, max_tokens=1000)

        return ChatResponse(
            reply=reply,
            reasoning=reasoning,
            sources=sources,
            query_used=current_query,
            queries_tried=queries_tried,
            iterations=len(queries_tried),
        )


_chat_agent: SceneSearchQAAgent | None = None


def get_chat_agent() -> SceneSearchQAAgent:
    """Return process-singleton SceneSearchQAAgent."""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = SceneSearchQAAgent()
    return _chat_agent
