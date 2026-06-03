"""Shared configuration and signed-token helpers for timestamped downloads.

The download pipeline expires links by *signing the filename with a timestamp*
(``itsdangerous.TimestampSigner``). Every access re-checks the age against
``DOWNLOAD_TTL_SECONDS``; once exceeded the signature raises ``SignatureExpired``
and the handler deletes the file. A background sweeper (see ``worker.py``)
removes files that expire without ever being requested.

Key/dir conventions are kept identical to ``metviz/common/download.py`` so the
Panel client and this server agree:
  * ``DOWNLOAD_SIGNING_KEY`` — HMAC key for the signer (env, dev fallback).
  * ``TSPLOT_DOWNLOAD``      — directory where generated files are stored.
"""

from __future__ import annotations

import base64
import os
import re
import uuid
from datetime import timedelta
from pathlib import Path

from itsdangerous import TimestampSigner

# Falls back to a clearly-insecure default for local dev only; set a real key
# (shared with the Panel app) in every deployed environment.
SIGNING_KEY: str = os.environ.get("DOWNLOAD_SIGNING_KEY", "insecure-dev-key")

# How long a download link stays valid, in seconds (default 10 minutes).
DOWNLOAD_TTL_SECONDS: int = int(os.environ.get("DOWNLOAD_TTL_SECONDS", "600"))


def download_dir() -> Path:
    """Return the configured download directory, creating it if needed."""
    path = Path(os.environ.get("TSPLOT_DOWNLOAD") or os.environ.get("DOWNLOAD_DIR", "/tmp/downloads"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_signer() -> TimestampSigner:
    """Return a signer bound to the configured key."""
    return TimestampSigner(SIGNING_KEY)


def new_filename(output_format: str) -> str:
    """Return a unique, URL-safe filename with the given extension."""
    raw = base64.b64encode(uuid.uuid4().bytes).decode("utf-8")
    unique = re.sub(r"[=+/]", lambda m: {"+": "-", "/": "_", "=": ""}[m.group(0)], raw)
    return f"{unique}.{output_format}"


def sign_filename(filename: str) -> str:
    """Sign a filename, returning the timestamped download token."""
    return get_signer().sign(filename).decode()


def unsign_token(token: str):
    """Verify a download token against the TTL.

    Returns ``(filename, expiry_datetime)``. ``itsdangerous`` hands back the
    instant the token was *signed*; the link expires ``DOWNLOAD_TTL_SECONDS``
    later, so we add the TTL to get the actual (UTC, tz-aware) expiry that the
    landing-page countdown ticks down to.

    Raises ``itsdangerous`` errors (``SignatureExpired`` / ``BadSignature``) on
    failure.
    """
    filename_bytes, signed_at = get_signer().unsign(
        token, max_age=DOWNLOAD_TTL_SECONDS, return_timestamp=True
    )
    expiry = signed_at + timedelta(seconds=DOWNLOAD_TTL_SECONDS)
    return filename_bytes.decode(), expiry


def file_for_token(token: str) -> Path:
    """Path to the stored file a token refers to (token = '<filename>.<sig>')."""
    # The token is the filename plus a '.<sig>' suffix; strip the signature.
    return download_dir() / token.rsplit(".", 2)[0]
