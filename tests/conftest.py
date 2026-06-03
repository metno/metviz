"""Shared fixtures: small in-memory xarray datasets standing in for the real
OPeNDAP feature types, so tests run offline.
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr


@pytest.fixture
def timeseries_ds() -> xr.Dataset:
    """A timeSeries-like dataset: one numeric var + QC + non-numeric + lat/lon."""
    time = pd.date_range("2020-01-01", periods=5, freq="D")
    ds = xr.Dataset(
        {
            "air_temperature": ("time", np.arange(5.0)),
            "air_temperature_qc": ("time", np.zeros(5)),
            "station_name": ("time", list("abcde")),
        },
        coords={
            "time": time,
            "latitude": ("time", np.linspace(60, 61, 5)),
            "longitude": ("time", np.linspace(10, 11, 5)),
        },
    )
    return ds


@pytest.fixture
def profile_ds() -> xr.Dataset:
    """A DSG profile-like dataset: depth lives in data_vars, no coords."""
    return xr.Dataset(
        {
            "sea_water_temperature": ("obs", np.linspace(10, 4, 6)),
            "depth": ("obs", np.linspace(0, 100, 6)),
        }
    )
