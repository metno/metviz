"""Offline tests for the timestamped download/export pipeline.

Covered:
  * signed-token round-trip, expiry and tamper detection (``signing``);
  * the background sweeper deleting aged files (``worker``);
  * ``POST /process_data`` returning a token, with Celery/Redis mocked out.

No broker, Redis server or network is required.
"""

import importlib
import time
from pathlib import Path

import pytest
from itsdangerous import BadSignature, SignatureExpired


@pytest.fixture
def signing(tmp_path, monkeypatch):
    """Reload ``signing`` with a temp download dir and known key/TTL."""
    monkeypatch.setenv("TSPLOT_DOWNLOAD", str(tmp_path))
    monkeypatch.setenv("DOWNLOAD_SIGNING_KEY", "test-key")
    monkeypatch.setenv("DOWNLOAD_TTL_SECONDS", "600")
    mod = importlib.import_module("signing")
    return importlib.reload(mod)


def test_token_roundtrip(signing):
    filename = signing.new_filename("nc")
    assert filename.endswith(".nc")

    token = signing.sign_filename(filename)
    recovered, _expiry = signing.unsign_token(token)
    assert recovered == filename


def test_token_expires(signing, monkeypatch):
    token = signing.sign_filename("data.csv")
    # Force a negative TTL so an immediately-issued token is already expired.
    monkeypatch.setattr(signing, "DOWNLOAD_TTL_SECONDS", -1)
    with pytest.raises(SignatureExpired):
        signing.unsign_token(token)


def test_token_tampered(signing):
    token = signing.sign_filename("data.csv")
    with pytest.raises(BadSignature):
        signing.unsign_token(token + "x")


def test_file_for_token_strips_signature(signing):
    token = signing.sign_filename("abc.nc")
    assert signing.file_for_token(token) == Path(signing.download_dir()) / "abc.nc"


def test_sweeper_removes_aged_files(tmp_path, monkeypatch):
    monkeypatch.setenv("TSPLOT_DOWNLOAD", str(tmp_path))
    worker = importlib.reload(importlib.import_module("worker"))

    fresh = tmp_path / "fresh.nc"
    fresh.write_text("x")
    stale = tmp_path / "stale.nc"
    stale.write_text("x")
    # Make the stale file older than the TTL.
    old = time.time() - (worker.DOWNLOAD_TTL_SECONDS + 100)
    import os

    os.utime(stale, (old, old))

    removed = worker.sweep_expired_downloads.run()
    assert removed == 1
    assert fresh.exists()
    assert not stale.exists()


def test_process_data_returns_token(tmp_path, monkeypatch):
    monkeypatch.setenv("TSPLOT_DOWNLOAD", str(tmp_path))
    monkeypatch.setenv("DOWNLOAD_SIGNING_KEY", "test-key")
    import download_api
    import main
    from fastapi.testclient import TestClient

    class _FakeTask:
        id = "fake-task-id"
        status = "PENDING"

    class _FakeProcess:
        @staticmethod
        def delay(_config):
            return _FakeTask()

    class _FakeRedis:
        def set(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(download_api, "process_data", _FakeProcess)
    monkeypatch.setattr(download_api, "redis_client", _FakeRedis())

    client = TestClient(main.app)
    resp = client.post(
        "/process_data",
        json={"url": "http://example/x.nc", "variables": ["t"], "output_format": "nc"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["task_id"] == "fake-task-id"
    assert body["filename"].endswith(".nc")
    # The returned token must verify back to the same filename.
    import signing as signing_mod

    recovered, _ = signing_mod.unsign_token(body["download_token"])
    assert recovered == body["filename"]
