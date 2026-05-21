import numpy as np
import pandas as pd
import xarray as xr
from plotting import (
    _apply_orientation,
    _datetime_coords,
    _first_var,
    _resolve_title,
    _should_invert_yaxis,
    plot_quadmesh,
)


def test_first_var_unwraps_list():
    assert _first_var(["temp"]) == "temp"
    assert _first_var("temp") == "temp"


def test_resolve_title_prefers_explicit(profile_ds):
    assert _resolve_title(profile_ds, "sea_water_temperature", "My Title") == "My Title"


def test_resolve_title_falls_back_to_long_name(profile_ds):
    profile_ds["sea_water_temperature"].attrs["long_name"] = "Sea Water Temperature"
    assert _resolve_title(profile_ds, "sea_water_temperature", None) == "Sea Water Temperature"


def test_should_invert_yaxis_for_depth(profile_ds):
    assert _should_invert_yaxis(profile_ds, "sea_water_temperature", "depth") is True


def test_should_invert_yaxis_honours_positive_down():
    ds = xr.Dataset(
        {"v": ("lev", np.arange(3.0))},
        coords={"lev": ("lev", np.arange(3.0))},
    )
    ds["lev"].attrs["positive"] = "down"
    assert _should_invert_yaxis(ds, "v", "lev") is True


def test_datetime_coords(timeseries_ds):
    assert _datetime_coords(timeseries_ds) == ["time"]


def _tsp_dataset() -> xr.Dataset:
    time = pd.date_range("2020-01-01", periods=4, freq="D")
    depth = np.array([0.0, 10.0, 20.0])
    data = np.arange(12.0).reshape(4, 3)
    return xr.Dataset(
        {"temperature": (("time", "depth"), data)},
        coords={"time": time, "depth": depth},
    )


def test_plot_quadmesh_returns_object_for_2d():
    import holoviews as hv

    result = plot_quadmesh("temperature", _tsp_dataset())
    assert isinstance(result, hv.QuadMesh)


def test_plot_quadmesh_returns_none_for_1d(timeseries_ds):
    assert plot_quadmesh("air_temperature", timeseries_ds) is None


# --- axis orientation dispatch (invert / swap) -----------------------------


class _RecordingPlot:
    """Stand-in for a HoloViews object: records the opts applied to it."""

    def __init__(self):
        self.applied = None

    def opts(self, **kw):
        self.applied = kw
        return self


class _Pane:
    def __init__(self, obj):
        self.object = obj


class _Layout(list):
    """Stand-in for a Panel layout: iterable and exposes `.objects`."""

    @property
    def objects(self):
        return list(self)


def test_apply_orientation_noop_without_flags():
    plot = _RecordingPlot()
    _apply_orientation(plot)
    assert plot.applied is None


def test_apply_orientation_on_bare_object():
    plot = _RecordingPlot()
    _apply_orientation(plot, invert_yaxis=True, swap_axes=True)
    assert plot.applied == {"invert_yaxis": True, "invert_axes": True}


def test_apply_orientation_on_panel_layout():
    # A layout with a slider-like item (no .object) and the plot pane.
    plot = _RecordingPlot()
    layout = _Layout([_Pane(None), _Pane(plot)])
    _apply_orientation(layout, invert_yaxis=True)
    assert plot.applied == {"invert_yaxis": True}
