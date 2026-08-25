"""Asynchronous OpenAI-compatible LLM client for agentic search tasks."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from core.config import get_settings


class LLMClient:
    """Lightweight asynchronous LLM client compatible with any OpenAI-style API."""

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def is_available(self) -> bool:
        """True if an API key is configured."""
        return bool(self._settings.llm.api_key and self._settings.llm.api_key.get_secret_value())

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int = 400,
        response_format: dict[str, str] | None = None,
    ) -> str | None:
        """Send a chat completion request to the configured LLM endpoint.

        Returns None if not available, timed out, or encountering any HTTP/API error.
        """
        if not self.is_available:
            return None

        api_key = self._settings.llm.api_key.get_secret_value()  # type: ignore[union-attr]
        base_url = self._settings.llm.base_url.rstrip("/")
        url = f"{base_url}/chat/completions"

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self._settings.llm.model,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else self._settings.llm.temperature
            ),
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        try:
            async with httpx.AsyncClient(timeout=self._settings.llm.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code != 200:
                    logger.warning(
                        "LLM API returned status {status}: {text}",
                        status=response.status_code,
                        text=response.text[:200],
                    )
                    return None
                data = response.json()
                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    return None
                content = choices[0].get("message", {}).get("content", "")
                return content.strip() if content else None
        except httpx.TimeoutException:
            logger.warning("LLM request timed out after {}s", self._settings.llm.timeout)
            return None
        except Exception as exc:
            logger.warning("LLM completion failed gracefully: {}", exc)
            return None


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return process-singleton LLMClient."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
