import importlib
from pathlib import Path


def test_generate_download_string(tmp_path, monkeypatch):
    monkeypatch.setenv("TSPLOT_DOWNLOAD", str(tmp_path))
    # _SIGNING_KEY is read at import time; reload so the env (if any) applies.
    download = importlib.import_module("common.download")
    importlib.reload(download)

    result = download.generate_download_string()
    assert isinstance(result, Path)
    assert result.parent == tmp_path
    # A signed token is "<filename>.<sig>"; the filename part ends in .csv.
    assert ".csv" in result.name
