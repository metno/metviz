"""Offline test for the download-link client helper (``common.download``)."""

import importlib


def test_get_download_link_builds_results_url(monkeypatch):
    """get_download_link forwards the spec and appends the returned token."""
    monkeypatch.setenv("PROCESSING_ENDPOINT", "http://proc:8000")
    monkeypatch.setenv("DOWNLOAD_ENDPOINT", "https://public.example/api")
    download = importlib.reload(importlib.import_module("common.download"))

    captured = {}

    class _Resp:
        @staticmethod
        def json():
            return {"download_token": "name_abc.nc.TS.SIG"}

    def _fake_post(url, data=None, **_kwargs):
        captured["url"] = url
        captured["data"] = data
        return _Resp()

    monkeypatch.setattr(download.requests, "post", _fake_post)

    link = download.get_download_link("{}")

    assert captured["url"] == "http://proc:8000/process_data"
    assert link == "https://public.example/api/results/name_abc.nc.TS.SIG"
