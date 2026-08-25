"""Admin telemetry and eval-report endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import require_admin
from db.models.review import User
from schemas.admin import AdminTelemetry, EmbeddingModelStatus, EvalReportResponse
from services.admin import collect_telemetry, load_eval_report
from services.embedding_model import embedding_model_request

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/telemetry", response_model=AdminTelemetry)
async def get_telemetry(_: Annotated[User, Depends(require_admin)]) -> AdminTelemetry:
    return await collect_telemetry()


@router.get("/eval", response_model=EvalReportResponse)
async def get_eval_report(_: Annotated[User, Depends(require_admin)]) -> EvalReportResponse:
    return load_eval_report()


@router.get("/embedding-model", response_model=EmbeddingModelStatus)
async def get_embedding_model_status(
    _: Annotated[User, Depends(require_admin)],
) -> EmbeddingModelStatus:
    return await embedding_model_request("status")


@router.post("/embedding-model/load", response_model=EmbeddingModelStatus)
async def load_embedding_model(
    _: Annotated[User, Depends(require_admin)],
) -> EmbeddingModelStatus:
    return await embedding_model_request("load")


@router.post("/embedding-model/unload", response_model=EmbeddingModelStatus)
async def unload_embedding_model(
    _: Annotated[User, Depends(require_admin)],
) -> EmbeddingModelStatus:
    return await embedding_model_request("unload")
