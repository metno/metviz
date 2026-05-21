import numpy as np
import pandas as pd
import pytest
import xarray as xr
from common.trajectory import (
    duration_hours,
    geodesic_length_km,
    latlon_names,
    nearest_index_for_time,
    to_datetime64,
    track_bounds,
    track_points,
)


def _traj_ds(lat_name="latitude", lon_name="longitude"):
    time = pd.date_range("2022-01-01", periods=3, freq="h")
    return xr.Dataset(
        {
            "air_temperature": ("time", [1.0, 2.0, 3.0]),
            lat_name: ("time", [60.0, 60.5, 61.0]),
            lon_name: ("time", [10.0, 10.5, 11.0]),
        },
        coords={"time": time},
    )


def test_latlon_names_variants():
    assert latlon_names(_traj_ds()) == ("latitude", "longitude")
    assert latlon_names(_traj_ds("lat", "lon")) == ("lat", "lon")


def test_track_points_and_bounds():
    points = track_points(_traj_ds())
    assert points == [[60.0, 10.0], [60.5, 10.5], [61.0, 11.0]]
    assert track_bounds(points) == [[60.0, 10.0], [61.0, 11.0]]


def test_track_points_empty_without_latlon():
    ds = xr.Dataset({"v": ("time", [1.0, 2.0])}, coords={"time": [0, 1]})
    assert track_points(ds) == []
    assert track_bounds([]) is None


def test_track_points_skips_nonfinite():
    ds = _traj_ds()
    ds["latitude"][1] = np.nan
    assert track_points(ds) == [[60.0, 10.0], [61.0, 11.0]]


def test_duration_hours():
    assert duration_hours(_traj_ds()) == pytest.approx(2.0)


def test_geodesic_length_positive():
    # ~moving NE across a few tenths of a degree -> tens of km, monotonic increase.
    length = geodesic_length_km(track_points(_traj_ds()))
    assert length > 0


def test_nearest_index_for_time_accepts_various_x_types():
    times = pd.date_range("2022-01-01", periods=5, freq="h").values
    # epoch ms (numeric)
    epoch_ms = int(times[2].astype("datetime64[ms]").astype("int64"))
    assert nearest_index_for_time(times, epoch_ms) == 2
    # a python datetime (what Bokeh actually passes for a datetime axis)
    assert nearest_index_for_time(times, pd.Timestamp(times[3]).to_pydatetime()) == 3
    # a numpy datetime64
    assert nearest_index_for_time(times, times[1]) == 1
    # 20 min past times[3] still snaps to 3
    near3 = int(times[3].astype("datetime64[ms]").astype("int64")) + 20 * 60 * 1000
    assert nearest_index_for_time(times, near3) == 3
    assert nearest_index_for_time(times, None) is None


def test_to_datetime64_handles_datetime_and_epoch():
    ts = pd.Timestamp("2022-01-01T03:00:00")
    assert to_datetime64(ts.to_pydatetime()) == np.datetime64("2022-01-01T03:00:00", "ms")
    epoch_ms = int(ts.value // 1_000_000)
    assert to_datetime64(epoch_ms) == np.datetime64("2022-01-01T03:00:00", "ms")
    assert to_datetime64(None) is None
