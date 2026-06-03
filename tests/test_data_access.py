"""Tests for the shared Download + Metadata component (common.data_access).

Focus on the export-spec assembly in ``_request_download`` (format mapping,
resampling decision, time-range handling, variable selection) and the basic
shape of the built panel. Requires the viz stack (panel).
"""

import json

import panel as pn
import pytest
from bokeh.models import Div

from common import data_access
from common.data_access import FREQUENCY_OPTIONS, build_data_access, _request_download


def _capture_link(monkeypatch):
    """Patch get_download_link to record the spec it is handed; return a getter."""
    captured = {}

    def fake(data):
        captured["spec"] = json.loads(data)
        return "https://host/results/tok"

    monkeypatch.setattr(data_access, "get_download_link", fake)
    return captured


def _widgets(*, frequency="--", fmt="CSV", with_time=True):
    checkboxes = pn.FlexBox(
        pn.widgets.Checkbox(name="ta", value=True),
        pn.widgets.Checkbox(name="hur", value=False),
    )
    if with_time:
        import numpy as np
        import pandas as pd

        t = pd.date_range("2020-01-01", periods=3, freq="D").values
        slider = pn.widgets.DatetimeRangeSlider(
            name="Date Range", start=t.min(), end=t.max(), value=(t.min(), t.max())
        )
    else:
        slider = Div(text="no time")
    return dict(
        checkbox_group=checkboxes,
        time_range_slider=slider,
        format_select=pn.widgets.Select(options=["NetCDF", "CSV", "Parquet"], value=fmt),
        frequency_select=pn.widgets.Select(options=FREQUENCY_OPTIONS, value=frequency),
        event_log=Div(),
    )


def test_request_download_builds_spec(monkeypatch):
    captured = _capture_link(monkeypatch)
    w = _widgets(frequency="Hourly", fmt="CSV")
    _request_download(url="http://data/x.nc", decoded_time=True, loading_target=None, **w)

    spec = captured["spec"]
    assert spec["url"] == "http://data/x.nc"
    assert spec["variables"] == ["ta"]          # only the checked box
    assert spec["output_format"] == "csv"        # label -> token
    assert spec["is_resampled"] is True
    assert spec["resampling_frequency"] == "Hourly"
    assert len(spec["time_range"]) == 2          # real slider -> [start, end]
    assert 'href="https://host/results/tok"' in w["event_log"].text


def test_request_download_raw_when_no_frequency(monkeypatch):
    captured = _capture_link(monkeypatch)
    w = _widgets(frequency="--", fmt="NetCDF")
    _request_download(url="u", decoded_time=True, loading_target=None, **w)

    spec = captured["spec"]
    assert spec["is_resampled"] is False
    assert spec["resampling_frequency"] == "raw"
    assert spec["output_format"] == "nc"


def test_request_download_no_time_slider(monkeypatch):
    captured = _capture_link(monkeypatch)
    w = _widgets(with_time=False)
    _request_download(url="u", decoded_time=True, loading_target=None, **w)
    assert captured["spec"]["time_range"] == []   # Div slider -> no range


def test_request_download_surfaces_errors(monkeypatch):
    def boom(_data):
        raise RuntimeError("processing service down")

    monkeypatch.setattr(data_access, "get_download_link", boom)
    w = _widgets()
    _request_download(url="u", decoded_time=True, loading_target=None, **w)
    assert "failed" in w["event_log"].text.lower()


def test_build_data_access_shape(timeseries_ds):
    panel = build_data_access(timeseries_ds, url="http://data/x.nc", variables=["air_temperature"])
    assert panel.download_button.label == "Download"
    assert panel.metadata_button.label == "Metadata"
    # Both panels start hidden until a header button reveals them.
    assert panel.download_panel.visible is False
    assert panel.metadata_panel.visible is False
