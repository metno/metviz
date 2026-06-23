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

# Per-task metadata stored in Redis (keyed by Celery task id) is only useful
# while a download is live; expire it a bit after the link so it self-cleans
# instead of accumulating forever.
TASK_META_TTL_SECONDS: int = DOWNLOAD_TTL_SECONDS * 2


def download_dir() -> Path:
    """Return the configured download directory, creating it if needed."""
    path = Path(os.environ.get("TSPLOT_DOWNLOAD") or os.environ.get("DOWNLOAD_DIR", "/tmp/downloads"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_signer() -> TimestampSigner:
    """Return a signer bound to the configured key."""
    return TimestampSigner(SIGNING_KEY)


def _slugify(text: str, maxlen: int = 60) -> str:
    """Reduce arbitrary text to a dot-free, URL/filesystem-safe slug.

    Dots are collapsed along with everything else non-alphanumeric: the signed
    token is ``<filename>.<timestamp>.<sig>``, so the filename must contain
    exactly one dot (the one before the extension) for the token to round-trip.
    """
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:maxlen].strip("-")


def new_filename(output_format: str, label: str = "") -> str:
    """Return a unique, URL-safe filename, optionally prefixed with a label.

    Shape: ``<slug>_<short-uid>.<ext>`` (or ``<short-uid>.<ext>`` when *label*
    is empty). *label* is a human hint (source dataset name + variables); it is
    slugified to stay dot-free so the signed token round-trips. The short random
    suffix keeps on-disk names unique; security is provided by the HMAC
    signature, not by the filename, so a short id is sufficient.
    """
    short_uid = uuid.uuid4().hex[:10]
    slug = _slugify(label)
    stem = f"{slug}_{short_uid}" if slug else short_uid
    return f"{stem}.{output_format}"


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


def filename_from_token(token: str) -> str:
    """Recover the signed filename **without** checking expiry.

    Used by cleanup paths (deleting the file behind an already-expired token),
    where the TTL check has already failed but we still need the name. Lets
    ``itsdangerous`` parse the signature rather than splitting on dots, so it
    stays correct even when the filename itself contains separators. Raises
    ``BadSignature`` if the token was tampered with.
    """
    return get_signer().unsign(token).decode()


def file_for_token(token: str) -> Path:
    """Path to the stored file a token refers to."""
    return download_dir() / filename_from_token(token)
