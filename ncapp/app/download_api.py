"""FastAPI router for the timestamped async download pipeline.

Endpoints (the route shapes are fixed by the existing Panel client in
``metviz/common/download.py``):

  POST /process_data           enqueue an export job; returns a download_token
  GET  /results/{token}        landing page with a live countdown + download link
  GET  /file_results/{token}   the actual bytes, refused (and deleted) once expired

Expiry is enforced by the signed token (see ``signing.py``); there is no static
file mount, so an expired link cannot be used to fetch the file.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired
from models import DatasetConfig, TaskResponse
from signing import (
    download_dir,
    file_for_token,
    new_filename,
    sign_filename,
    unsign_token,
)
from worker import process_data, redis_client

router = APIRouter()

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)


@router.post("/process_data", status_code=201, response_model=TaskResponse)
def enqueue_process_data(
    payload: DatasetConfig = Body(..., examples=[DatasetConfig.model_config["json_schema_extra"]["example"]]),
):
    """Sign a target filename, enqueue the export job, return the download token."""
    config = payload.model_dump(mode="json")
    filename = new_filename(config.get("output_format", "nc"))
    download_token = sign_filename(filename)

    config["filename"] = filename
    config["download_token"] = download_token

    task = process_data.delay(config)
    redis_client.set(task.id, json.dumps({"download_token": download_token, "filename": filename}))

    return {
        "task_id": task.id,
        "download_token": download_token,
        "filename": filename,
        "task_status": task.status,
    }


@router.get("/results/{download_token}")
async def download_landing(request: Request, download_token: str):
    """Render the download landing page (with countdown), or the expired page."""
    try:
        filename, expiry = unsign_token(download_token)
    except SignatureExpired:
        _remove_expired(download_token)
        return templates.TemplateResponse(
            "expired.html",
            {"request": request, "id": download_token, "error": "The download link has expired."},
        )
    except BadSignature as exc:
        return templates.TemplateResponse(
            "error.html", {"request": request, "id": download_token, "error": str(exc)}
        )

    return templates.TemplateResponse(
        "download.html",
        {
            "request": request,
            "token": download_token,
            "filename": filename,
            # The countdown JS reconstructs the expiry instant from these parts.
            "year": expiry.year,
            "month": expiry.month - 1,  # JS Date months are 0-based
            "day": expiry.day,
            "hour": expiry.hour,
            "minute": expiry.minute,
            "second": expiry.second,
        },
    )


@router.get("/file_results/{download_token}")
async def serve_file(request: Request, download_token: str):
    """Return the file bytes if the token is still valid, else delete + expire."""
    try:
        unsign_token(download_token)
    except SignatureExpired:
        _remove_expired(download_token)
        return templates.TemplateResponse(
            "expired.html",
            {"request": request, "id": download_token, "error": "The download link has expired."},
        )
    except BadSignature as exc:
        return templates.TemplateResponse(
            "error.html", {"request": request, "id": download_token, "error": str(exc)}
        )

    path = file_for_token(download_token)
    if not path.is_file():
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "id": download_token, "error": "File not found (still processing or removed)."},
        )
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


def _remove_expired(download_token: str) -> None:
    """Best-effort delete of the file backing an expired token."""
    try:
        (download_dir() / download_token.rsplit(".", 2)[0]).unlink()
    except OSError:
        pass
