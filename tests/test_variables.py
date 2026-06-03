import numpy as np
import xarray as xr

from common.variables import (
    get_axis_candidates,
    get_plottable_vars,
    is_empty,
    is_plottable,
    is_time_like,
    sort_axis_candidates,
)


def test_is_plottable_rules(timeseries_ds):
    assert is_plottable("air_temperature", timeseries_ds["air_temperature"])
    # QC suffix excluded
    assert not is_plottable("air_temperature_qc", timeseries_ds["air_temperature_qc"])
    # non-numeric excluded
    assert not is_plottable("station_name", timeseries_ds["station_name"])
    # coordinate-like name excluded
    assert not is_plottable("latitude", timeseries_ds["latitude"])


def test_get_plottable_vars_timeseries(timeseries_ds):
    assert get_plottable_vars(timeseries_ds) == ["air_temperature"]


def test_get_plottable_vars_profile(profile_ds):
    # depth is coordinate-like by name and must not appear as a plottable var.
    assert get_plottable_vars(profile_ds) == ["sea_water_temperature"]


def test_axis_candidates_timeseries_excludes_latlon(timeseries_ds):
    candidates = get_axis_candidates(timeseries_ds, "air_temperature")
    assert "time" in candidates
    assert "latitude" not in candidates  # AXIS_BLACKLIST
    assert "longitude" not in candidates


def test_axis_candidates_profile_finds_depth(profile_ds):
    candidates = get_axis_candidates(profile_ds, "sea_water_temperature")
    assert "depth" in candidates
    # never offer another data variable as an axis
    assert "sea_water_temperature" not in candidates


def test_is_time_like(timeseries_ds):
    assert is_time_like(timeseries_ds, "time")
    assert not is_time_like(timeseries_ds, "latitude")


def test_sort_axis_candidates_time_first(timeseries_ds):
    assert sort_axis_candidates(timeseries_ds, ["latitude", "time"])[0] == "time"


def test_is_empty_all_nan():
    ds = xr.Dataset({"x": ("t", [np.nan] * 5)})
    assert is_empty(ds, "x")


def test_is_empty_all_fill_value():
    ds = xr.Dataset({"x": ("t", [9.96921e36] * 5)})
    assert is_empty(ds, "x")


def test_is_empty_mixed_real_and_missing():
    ds = xr.Dataset({"x": ("t", [1.0, np.nan, 9.96921e36, 2.0])})
    assert not is_empty(ds, "x")


def test_is_empty_normal_values():
    ds = xr.Dataset({"x": ("t", np.arange(5.0))})
    assert not is_empty(ds, "x")


def test_is_empty_missing_variable_returns_false():
    """Conservative fallback: if we can't inspect, treat as non-empty."""
    ds = xr.Dataset({"x": ("t", np.arange(3.0))})
    assert not is_empty(ds, "does_not_exist")
