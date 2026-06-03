"""Tests for the dependency-light data-prep core shared by the plot path and the
export worker. All offline (no OPeNDAP).
"""

import numpy as np
import pandas as pd
import xarray as xr
from common.dataprep import (
    FILL_VALUE,
    datetime_coords,
    is_monotonic,
    mask_fill,
    pandas_frequency_offsets,
)


def test_datetime_coords_finds_time(timeseries_ds):
    assert datetime_coords(timeseries_ds) == ["time"]


def test_datetime_coords_none_when_absent(profile_ds):
    assert datetime_coords(profile_ds) == []


def test_is_monotonic_increasing(timeseries_ds):
    assert is_monotonic(timeseries_ds) is True


def test_is_monotonic_none_without_time(profile_ds):
    assert is_monotonic(profile_ds) is None


def test_mask_fill_replaces_sentinel_with_nan():
    da = xr.DataArray([1.0, FILL_VALUE, 2.0])
    masked = mask_fill(da)
    assert np.isnan(masked.values[1])
    assert masked.values[0] == 1.0 and masked.values[2] == 2.0


def test_mask_fill_works_on_dataset():
    ds = xr.Dataset({"a": ("t", [1.0, FILL_VALUE]), "b": ("t", [FILL_VALUE, 3.0])})
    masked = mask_fill(ds)
    assert np.isnan(masked["a"].values[1])
    assert np.isnan(masked["b"].values[0])


def test_frequency_table_matches_plotting():
    # Single source of truth: the plot path re-exports the same table.
    from common.plotting import pandas_frequency_offsets as plot_offsets

    assert pandas_frequency_offsets is plot_offsets
    assert pandas_frequency_offsets["Hourly"] == "h"


def test_fill_value_single_source():
    from common.plotting import FILL_VALUE as plot_fill
    from common.variables import _FILL_VALUE as var_fill

    assert plot_fill == FILL_VALUE == var_fill
