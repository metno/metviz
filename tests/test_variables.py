from common.variables import (
    get_axis_candidates,
    get_plottable_vars,
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
