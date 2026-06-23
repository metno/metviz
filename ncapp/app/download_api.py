"""FastAPI router for the timestamped async download pipeline.

Endpoints (the route shapes are fixed by the existing Panel client in
``metviz/common/download.py``):

  POST /process_data           enqueue an export job; returns a download_token
  GET  /results/{token}        landing page: countdown + link, or processing/failed/expired
  GET  /file_results/{token}   the actual bytes, refused (and deleted) once expired

Expiry is anchored to the generated file's mtime (``signing.file_expiry``), so
the countdown only starts once the worker has written the file. There is no
static file mount, so an expired link cannot be used to fetch the file. Export
failures are recorded in Redis (``worker.read_status``) and surfaced here.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature
from models import DatasetConfig, TaskResponse
from signing import (
    download_dir,
    file_expiry,
    filename_from_token,
    new_filename,
    sign_filename,
)
from worker import process_data, read_status

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

    return {
        "task_id": task.id,
        "download_token": download_token,
        "filename": filename,
        "task_status": task.status,
    }


def _now() -> datetime:
    return datetime.now(UTC)


def _unlink(path: Path) -> None:
    """Best-effort delete of a generated file."""
    try:
        path.unlink()
    except OSError:
        pass


def _page(request: Request, name: str, **context):
    """Render a template using the current (request-first) Starlette signature."""
    return templates.TemplateResponse(request, name, context)


def _failed_page(request: Request, token: str, reason: str):
    return _page(request, "error.html", id=token, error=f"Export failed: {reason}")


def _expired_page(request: Request, token: str):
    return _page(request, "expired.html", id=token, error="The download link has expired.")


@router.get("/results/{download_token}")
async def download_landing(request: Request, download_token: str):
    """Landing page: live countdown + download link, or processing / failed / expired."""
    try:
        filename = filename_from_token(download_token)
    except BadSignature as exc:
        return _page(request, "error.html", id=download_token, error=str(exc))

    status = read_status(download_token)
    if status.get("status") == "FAILED":
        return _failed_page(request, download_token, status.get("error") or "unknown error")

    path = download_dir() / filename
    expiry = file_expiry(path)
    if expiry is None:
        # File not written yet — the export is still running; this page refreshes.
        return _page(request, "processing.html", id=download_token, filename=filename)
    if expiry <= _now():
        _unlink(path)
        return _expired_page(request, download_token)

    return _page(
        request,
        "download.html",
        token=download_token,
        filename=filename,
        # The countdown JS reconstructs the expiry instant (file mtime + TTL).
        year=expiry.year,
        month=expiry.month - 1,  # JS Date months are 0-based
        day=expiry.day,
        hour=expiry.hour,
        minute=expiry.minute,
        second=expiry.second,
    )


@router.get("/file_results/{download_token}")
async def serve_file(request: Request, download_token: str):
    """Return the bytes when ready and unexpired; else processing / failed / expired."""
    try:
        filename = filename_from_token(download_token)
    except BadSignature as exc:
        return _page(request, "error.html", id=download_token, error=str(exc))

    status = read_status(download_token)
    if status.get("status") == "FAILED":
        return _failed_page(request, download_token, status.get("error") or "unknown error")

    path = download_dir() / filename
    expiry = file_expiry(path)
    if expiry is None:
        return _page(request, "error.html", id=download_token, error="File not ready yet (still processing).")
    if expiry <= _now():
        _unlink(path)
        return _expired_page(request, download_token)
    return FileResponse(path, media_type=_media_type(filename), filename=path.name)
