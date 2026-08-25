"""Export an engineer-selected dataset as a zip of clips + JSONL manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from api.deps import require_engineer_or_admin
from db.models.review import User
from schemas.datasets import DatasetExportRequest
from services.datasets import build_export_zip

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _unlink(path: str) -> None:
    Path(path).unlink(missing_ok=True)


@router.post("/export")
async def export_dataset(
    request: DatasetExportRequest,
    _: Annotated[User, Depends(require_engineer_or_admin)],
) -> FileResponse:
    zip_path = await build_export_zip(request)
    filename = f"{request.dataset_id}.zip"
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(_unlink, str(zip_path)),
    )
