"""Multimodal Conversational QA API endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from schemas.chat import ChatRequest, ChatResponse
from services.chat_agent import get_chat_agent

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="Chat with SceneSearch Multimodal AI Agent")
async def chat_with_agent(request: ChatRequest) -> ChatResponse:
    """Send a conversation message to SceneSearch Multimodal QA Agent.

    The agent will analyze the query, retrieve relevant scenes from Qdrant,
    inspect the keyframe images using NVIDIA Nemotron Omni VLM, and return
    a grounded answer with visual evidence and citations.
    """
    try:
        agent = get_chat_agent()
        return await agent.chat(request)
    except Exception as exc:
        logger.exception("Chat Agent error: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat Agent processing failed: {exc}",
        ) from exc
