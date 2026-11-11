"""Multimodal Conversational Video QA Agent with Multilingual Query Formulation and Visual Inspection."""

from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Any

import httpx
from loguru import logger
from PIL import Image

from core.config import get_settings
from ml.image_cache import get_image_cache
from schemas.chat import ChatRequest, ChatResponse, SceneSource
from search.engine import get_search_engine

FORMULATION_SYSTEM_PROMPT = """You are an expert video retrieval query planner for the SceneSearch traffic and dashcam system.

Your task:
1. Analyze the user's question or search intent (which is in Vietnamese or English).
2. Translate and distill the core visual concept into a concise, descriptive ENGLISH visual search query optimized for Qwen / SigLIP dense vector embeddings.
   - Example 1: "có video người đi bộ dắt chó nào không? họ là nam hay nữ và lúc đó họ mặc áo màu gì?" -> "person walking a dog on street or sidewalk"
   - Example 2: "tìm xe buýt màu vàng rẽ trái lúc trời mưa" -> "yellow bus turning left on wet rainy street"
   - Example 3: "bãi đỗ xe ô tô ban đêm" -> "outdoor parking lot with parked cars at night"
   - Example 4: "tai nạn va chạm xe máy ngã tư" -> "motorcycle traffic collision at intersection"
3. Strip away conversational follow-up questions (e.g. "họ là nam hay nữ", "mặc áo màu gì", "lúc đó là mấy giờ") from the vector search query, keeping ONLY the physical scene elements to be retrieved from the video database.

Output ONLY a raw JSON object (no markdown, no extra text):
{
  "needs_search": true,
  "search_query": "concise English visual query",
  "reason": "short explanation under 15 words"
}
"""

PARAPHRASE_SYSTEM_PROMPT = """You are an expert video retrieval query optimizer.
The previous search query returned zero or insufficient matches from the video database.
Analyze why it may have been too narrow and generate a broader, more effective visual search phrase in English while preserving driving/traffic/street context.

Output ONLY a raw JSON object:
{
  "search_query": "broader English visual search query",
  "reason": "short explanation of the refinement"
}
"""

QA_SYSTEM_PROMPT = """Bạn là Trợ lý AI Đa phương thức SceneSearch - Chuyên gia phân tích video giao thông và camera hành trình.
Bạn sử dụng mô hình thị giác (Vision-Language) để TRỰC TIẾP QUAN SÁT các khung hình ảnh trích xuất từ video.

YÊU CẦU QUAN TRỌNG VỀ PHONG CÁCH TRẢ LỜI:
1. LUÔN TRẢ LỜI BẰNG TIẾNG VIỆT tự nhiên, súc tích, ngắn gọn (chỉ từ 2 - 4 câu), đi thẳng trực tiếp vào câu trả lời chính của người dùng.
2. TUYỆT ĐỐI KHÔNG LIỆT KÊ HAY MÔ TẢ DÀI DÒNG LẦN LƯỢT TỪNG ẢNH [Scene 1], [Scene 2]... [Scene 10]. (Vì giao diện web đã tự động hiển thị các thẻ video/ảnh trích xuất ở ngay bên dưới câu trả lời của bạn để người dùng xem).
3. HÃY TỔNG HỢP KẾT LUẬN VÀ TRÍCH DẪN NGẮN:
   - Trả lời rõ câu hỏi (có thấy đối tượng không, đối tượng đang làm gì, màu sắc/đặc điểm gì, ở cảnh nào).
   - Chỉ dẫn chứng ngắn gọn phân cảnh liên quan nhất, ví dụ: "Phát hiện thấy xe màu vàng đang dừng chờ đèn đỏ ở [Scene 1] (lúc 00:15)."
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
        max_tokens: int = 1200,
        response_format: dict[str, str] | None = None,
        fallback_models: list[str] | None = None,
    ) -> tuple[str, str | None]:
        settings = get_settings()
        llm = settings.llm
        api_key = ""
        if llm.api_key:
            api_key = llm.api_key.get_secret_value().strip()
        if not api_key:
            api_key = (
                os.getenv("LLM_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or os.getenv("NVIDIA_API_KEY")
                or ""
            ).strip()

        if not api_key:
            raise RuntimeError(
                "LLM_API_KEY is not configured in environment. Please set LLM_API_KEY in app/.env"
            )

        base_url = (
            os.getenv("LLM_BASE_URL") or llm.base_url or "https://integrate.api.nvidia.com/v1"
        ).rstrip("/")
        model = os.getenv("LLM_MODEL") or llm.model or "nvidia/nemotron-3.5-super-vl-120b-a12b"
        url = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        client_timeout = httpx.Timeout(45.0, connect=10.0, read=45.0, write=20.0)

        models_to_try = [model]
        if fallback_models:
            models_to_try.extend([m for m in fallback_models if m != model])
        else:
            for default_alt in ["nvidia/nemotron-3.5-super-vl-120b-a12b"]:
                if default_alt != model:
                    models_to_try.append(default_alt)

        last_exc: Exception | None = None

        async with httpx.AsyncClient(timeout=client_timeout) as client:
            for model_name in models_to_try:
                payload: dict[str, Any] = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
                if response_format:
                    payload["response_format"] = response_format

                try:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code != 200:
                        logger.warning(
                            "Model {} returned error status {}: {}; attempting fallback...",
                            model_name,
                            response.status_code,
                            response.text[:200],
                        )
                        last_exc = RuntimeError(f"Model {model_name} status {response.status_code}")
                        continue

                    data = response.json()
                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    message = choices[0].get("message", {})
                    content = message.get("content", "") or ""
                    reasoning = message.get("reasoning_content") or choices[0].get(
                        "reasoning_content"
                    )
                    return content.strip(), reasoning
                except (httpx.TimeoutException, httpx.RequestError) as exc:
                    logger.warning(
                        "Model {} connection/timeout error: {}; attempting fallback...",
                        model_name,
                        exc,
                    )
                    last_exc = exc
                    continue

        if last_exc:
            raise last_exc
        return "", None

    def _image_to_data_url(self, img: Image.Image, max_edge: int = 640, quality: int = 85) -> str:
        """Resize PIL Image and convert to high-clarity base64 JPEG data URL (~50-80KB)."""
        w, h = img.size
        if max(w, h) > max_edge:
            scale = max_edge / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"

    async def _paraphrase_query(self, failed_query: str, user_original: str) -> str:
        """Reflect and generate an alternative visual search query."""
        messages = [
            {"role": "system", "content": PARAPHRASE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f'Original user question: "{user_original}"\n'
                    f'Previous vector query that returned low/zero results: "{failed_query}"\n'
                    f"Please generate an improved, broader English visual search phrase."
                ),
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
        """Process chat message end-to-end with query translation, iterative retrieval, and multi-image inspection."""
        engine = get_search_engine()
        image_cache = get_image_cache()

        # -------------------------------------------------------------
        # STEP 1: Query Formulation & Intent Translation (Tiếng Việt -> English Visual Query)
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

        # Non-search conversational greetings / inquiries
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
                "Chat Agent iteration {}/{} executing vector search for query: {!r}",
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

            if outcome.matches and len(outcome.matches) > 0:
                best_outcome = outcome
                break
            else:
                best_outcome = outcome
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
                    "content": (
                        f"Câu hỏi của người dùng: {request.message}\n"
                        f"(Thông báo hệ thống: Tìm kiếm vector với các từ khóa {queries_tried} không tìm thấy kết quả phù hợp trong cơ sở dữ liệu video. "
                        f"Hãy trả lời bằng tiếng Việt lịch sự, thông báo không tìm thấy đoạn video phù hợp và gợi ý các từ khóa khác)."
                    ),
                },
            ]
            content, reasoning = await self._call_vlm(no_results_messages, max_tokens=500)
            return ChatResponse(
                reply=content,
                reasoning=reasoning,
                sources=[],
                query_used=current_query,
                queries_tried=queries_tried,
                iterations=len(queries_tried),
            )

        # -------------------------------------------------------------
        # STEP 3: Visual Keyframe Acquisition from Storage / Cache
        # -------------------------------------------------------------
        candidate_matches = final_outcome.matches[: request.limit]
        items_to_fetch = []
        for match in candidate_matches:
            kf = match.keyframe
            frame_name = (
                kf.thumbnail_key.rsplit("/", 1)[-1]
                if kf.thumbnail_key
                else f"frame_{max(0, kf.frame_no):05d}.jpg"
            )
            items_to_fetch.append((str(kf.video_id or ""), frame_name))

        images = await image_cache.get_images_batch(items_to_fetch)

        # -------------------------------------------------------------
        # STEP 4: Multimodal Visual Inspection & Synthesis with Kimi-k3
        # -------------------------------------------------------------
        sources: list[SceneSource] = []
        user_content_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"Câu hỏi của người dùng: {request.message}\n\n"
                    f"Hệ thống đã truy xuất được {len(candidate_matches)} đoạn video/scene tiềm năng từ cơ sở dữ liệu (từ khóa truy vấn: '{current_query}').\n"
                    f"Dưới đây là thông tin và hình ảnh khung hình thực tế của từng scene:\n"
                ),
            }
        ]

        for idx, (match, img) in enumerate(zip(candidate_matches, images), start=1):
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
                    ts_end_s=kf.end_timestamp_s,
                    caption=kf.caption,
                    preview_url=preview_url,
                    clip_url=clip_url,
                    score=float(match.score) if match.score is not None else None,
                )
            )

            scene_desc = (
                f"\n=== [Scene {idx}] ===\n"
                f"• Video ID: {kf.video_id}\n"
                f"• Mốc thời gian: {timecode} ({kf.timestamp_s:.1f}s)\n"
                f"• Độ tương đồng vector: {float(match.score or 0.0):.3f}\n"
                f"• Chú thích hệ thống: {kf.caption or 'N/A'}\n"
                f"• Hình ảnh thực tế của [Scene {idx}]:"
            )
            user_content_blocks.append({"type": "text", "text": scene_desc})

            # Attach visual keyframe for Kimi-k3 multimodal vision inspection (all top candidate scenes up to 10)
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
                    "\nHÃY TỔNG HỢP BẰNG CHỨNG THỊ GIÁC VÀ TRẢ LỜI CÂU HỎI CỦA NGƯỜI DÙNG BẰNG TIẾNG VIỆT:\n"
                    "1. Trả lời súc tích, ngắn gọn (2-4 câu), tập trung thẳng vào câu trả lời chính của người dùng.\n"
                    "2. TUYỆT ĐỐI KHÔNG liệt kê mô tả dài dòng từng ảnh [Scene 1]... [Scene 10] (vì web đã có thẻ video bên dưới).\n"
                    "3. Chỉ dẫn chứng ngắn gọn phân cảnh phù hợp nhất kèm mốc thời gian."
                ),
            }
        )

        qa_messages: list[dict[str, Any]] = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
        ]
        for msg in request.history[-4:]:
            qa_messages.append({"role": msg.role, "content": msg.content})
        qa_messages.append({"role": "user", "content": user_content_blocks})

        try:
            reply, reasoning = await self._call_vlm(qa_messages, temperature=0.2, max_tokens=1200)
        except Exception as exc:
            logger.warning(
                "Multimodal VLM vision call failed ({}); falling back to text-only metadata QA", exc
            )
            # Fallback to pure text metadata QA without image attachments to prevent 500 errors
            text_only_blocks = [b for b in user_content_blocks if b.get("type") == "text"]
            fallback_messages = [
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                *[{"role": msg.role, "content": msg.content} for msg in request.history[-4:]],
                {"role": "user", "content": text_only_blocks},
            ]
            try:
                reply, reasoning = await self._call_vlm(
                    fallback_messages, temperature=0.2, max_tokens=800
                )
            except Exception as final_exc:
                logger.error("Fallback text QA also failed: {}", final_exc)
                # Formulate a direct fallback response from candidate scene metadata
                scene_summaries = []
                for s_idx, match in enumerate(candidate_matches, start=1):
                    kf = match.keyframe
                    timecode = f"{int(kf.timestamp_s // 60):02d}:{int(kf.timestamp_s % 60):02d}"
                    scene_summaries.append(
                        f"- [Scene {s_idx}] lúc {timecode}: {kf.caption or 'Khung cảnh video phù hợp'}"
                    )

                reply = (
                    f"Hệ thống đã tìm thấy {len(candidate_matches)} đoạn video tiềm năng phù hợp với câu hỏi của bạn:\n\n"
                    + "\n".join(scene_summaries)
                    + "\n\nBạn có thể nhấn trực tiếp vào các thẻ video bên dưới để xem chi tiết đoạn video trích xuất."
                )
                reasoning = "Phản hồi tự động từ metadata video do máy chủ LLM đang bận."

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
