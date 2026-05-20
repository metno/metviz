"""Download-token generation and the link to the external processing service."""

from __future__ import annotations

import base64
import os
import re
import uuid
from pathlib import Path

import requests
from itsdangerous import TimestampSigner

# Signing key for download tokens. Read from the environment so the secret is
# not baked into the source; falls back to a clearly-insecure default for local
# development only.
_SIGNING_KEY = os.environ.get("DOWNLOAD_SIGNING_KEY", "insecure-dev-key")


def generate_download_string() -> Path:
    """Return a signed, URL-safe output path for a generated download file.

    The filename is a random UUID (base64, URL-safe) and is signed with a
    timestamp so the processing service can verify and expire it.
    """
    output_format = "csv"
    raw = base64.b64encode(uuid.uuid4().bytes).decode("utf-8")
    unique = re.sub(r"[=+/]", lambda m: {"+": "-", "/": "_", "=": ""}[m.group(0)], raw)
    filename = f"{unique}.{output_format}"
    token = TimestampSigner(_SIGNING_KEY).sign(filename).decode()
    return Path(os.environ["TSPLOT_DOWNLOAD"], token)


def get_download_link(data: str) -> str:
    """POST a JSON data-spec to the processing service and return a download URL.

    ``data`` is the serialised export specification; the service responds with a
    ``download_token`` that is appended to the configured download endpoint.
    """
    processing_endpoint = os.environ["PROCESSING_ENDPOINT"]
    download_endpoint = os.environ["DOWNLOAD_ENDPOINT"]
    response = requests.post(f"{processing_endpoint}/process_data", data=data)
    token = response.json()["download_token"]
    return f"{download_endpoint}/results/{token}"
