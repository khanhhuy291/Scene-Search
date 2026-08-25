"""Pydantic schemas for the Conversational Multimodal QA Chatbot."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """Single turn in a conversation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    """Incoming user chat message with conversation history."""

    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(
        ..., min_length=1, max_length=2000, description="User question or search prompt"
    )
    history: list[ChatMessage] = Field(
        default_factory=list, description="Previous conversation turns"
    )
    limit: int = Field(default=3, ge=1, le=10, description="Number of candidate scenes to inspect")


class SceneSource(BaseModel):
    """Citations and media references for scenes examined by the agent."""

    model_config = ConfigDict(str_strip_whitespace=True)

    video_id: str
    frame_id: str
    point_id: str | None = None
    timestamp: str | None = None
    timestamp_s: float | None = None
    caption: str | None = None
    preview_url: str | None = None
    clip_url: str | None = None
    score: float | None = None


class ChatResponse(BaseModel):
    """Agent response containing answer, reasoning trace, and cited scenes."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reply: str
    reasoning: str | None = None
    sources: list[SceneSource] = Field(default_factory=list)
    query_used: str | None = None
    queries_tried: list[str] = Field(default_factory=list)
    iterations: int = 1
