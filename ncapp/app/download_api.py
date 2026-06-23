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
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired
from models import DatasetConfig, TaskResponse
from signing import (
    TASK_META_TTL_SECONDS,
    download_dir,
    filename_from_token,
    new_filename,
    sign_filename,
    unsign_token,
)
from worker import process_data, redis_client

router = APIRouter()

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)

# Content type by output extension, so the browser/OS recognises the file
# instead of treating every download as an opaque octet-stream.
_MEDIA_TYPES = {
    ".nc": "application/x-netcdf",
    ".csv": "text/csv",
    ".pq": "application/vnd.apache.parquet",
    ".parquet": "application/vnd.apache.parquet",
}


def _media_type(filename: str) -> str:
    """Best-effort content type from the file extension."""
    return _MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def _download_label(config: dict) -> str:
    """Human hint for the download filename: source dataset name + variables.

    Slugification happens in ``new_filename``; here we just assemble the parts.
    """
    source = os.path.splitext(os.path.basename(urlparse(unquote(config.get("url") or "")).path))[0]
    variables = config.get("variables") or []
    var_part = "-".join(variables[:3])
    base = source or "metviz"
    return f"{base}_{var_part}" if var_part else base


@router.post("/process_data", status_code=201, response_model=TaskResponse)
def enqueue_process_data(
    payload: DatasetConfig = Body(..., examples=[DatasetConfig.model_config["json_schema_extra"]["example"]]),
):
    """Sign a target filename, enqueue the export job, return the download token."""
    config = payload.model_dump(mode="json")
    filename = new_filename(config.get("output_format", "nc"), _download_label(config))
    download_token = sign_filename(filename)

    config["filename"] = filename
    config["download_token"] = download_token

    task = process_data.delay(config)
    # Expiring TTL so per-task metadata self-cleans instead of growing forever.
    redis_client.set(
        task.id,
        json.dumps({"download_token": download_token, "filename": filename}),
        ex=TASK_META_TTL_SECONDS,
    )

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
        filename, _expiry = unsign_token(download_token)
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

    path = download_dir() / filename
    if not path.is_file():
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "id": download_token, "error": "File not found (still processing or removed)."},
        )
    return FileResponse(path, media_type=_media_type(filename), filename=path.name)


def _remove_expired(download_token: str) -> None:
    """Best-effort delete of the file backing an (expired) token."""
    try:
        (download_dir() / filename_from_token(download_token)).unlink()
    except (OSError, BadSignature):
        pass
