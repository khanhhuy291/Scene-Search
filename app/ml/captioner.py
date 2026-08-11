"""Ollama Qwen3-VL vision captioning service for keyframes."""

from __future__ import annotations

import base64
import io
import os
import logging
from typing import List, Optional
import requests
from PIL import Image

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.environ.get("QWEN_MODEL", "qwen3-vl:2b-instruct")

PROMPT_TEMPLATE = """Analyze this video keyframe concisely for video scene search and retrieval.
Describe:
1. Main objects, vehicles, pedestrians, or scene components.
2. Traffic layout, road conditions, signs, and signals if applicable.
3. Environment, weather, lighting, and time of day.
4. Perceived actions, movement, or dynamics.

Keep description compact, clear, and rich in descriptive keywords (English)."""


class QwenVLCaptioner:
    """Connects to local Ollama API to generate detailed Qwen3-VL text descriptions for keyframes."""

    def __init__(self, model_name: str = MODEL_NAME, ollama_url: str = OLLAMA_URL) -> None:
        self.model_name = model_name
        self.ollama_url = ollama_url.rstrip("/")

    @staticmethod
    def _image_to_b64(img: Image.Image) -> str:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def generate_caption(self, image: Image.Image, timeout: int = 60) -> Optional[str]:
        """Generate text description for a single PIL image."""
        try:
            b64_str = self._image_to_b64(image)
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": PROMPT_TEMPLATE,
                        "images": [b64_str]
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "max_tokens": 256
                }
            }

            url = f"{self.ollama_url}/api/chat"
            response = requests.post(url, json=payload, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                caption = data.get("message", {}).get("content", "").strip()
                return caption if caption else None
            else:
                logger.warning(f"Ollama API returned status {response.status_code}: {response.text[:100]}")
                return None
        except Exception as exc:
            logger.warning(f"Ollama captioning failed: {exc}")
            return None
