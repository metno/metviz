"""Download-link client: POST the export spec to the processing service.

The processing service (``ncapp``) generates and signs the output filename and
returns a ``download_token``; this module just forwards the spec and assembles
the user-facing ``/results`` URL from it.
"""

from __future__ import annotations

import os

import requests


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
