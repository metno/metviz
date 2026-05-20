import numpy as np
import pandas as pd
import xarray as xr
from common.data import is_monotonic


def test_is_monotonic_increasing(timeseries_ds):
    assert is_monotonic(timeseries_ds) is True


def test_is_monotonic_decreasing():
    time = pd.date_range("2020-01-01", periods=5, freq="D")[::-1]
    ds = xr.Dataset({"v": ("time", np.arange(5.0))}, coords={"time": time})
    assert is_monotonic(ds) is True


def test_is_monotonic_unsorted():
    time = pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-02"])
    ds = xr.Dataset({"v": ("time", np.arange(3.0))}, coords={"time": time})
    assert is_monotonic(ds) is False


def test_is_monotonic_no_time_returns_none():
    ds = xr.Dataset({"v": ("x", np.arange(3.0))}, coords={"x": np.arange(3)})
    assert is_monotonic(ds) is None
