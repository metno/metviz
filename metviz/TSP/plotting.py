"""Plotting functions for the TSP app (timeSeries / profile / timeSeriesProfile).

These functions are deliberately free of UI/global state: they take the dataset
and the user's choices as explicit arguments and return a HoloViews/Panel
object. Widget wiring lives in ``main.py``.
"""

from __future__ import annotations

import holoviews as hv
import hvplot.xarray  # noqa: F401  (registers the `.hvplot` accessor)
import numpy as np
import xarray as xr

# NetCDF standard missing/fill value used by many CF-convention datasets.
FILL_VALUE = 9.96921e36

# Map the resampling-frequency labels shown in the UI to pandas offset aliases.
pandas_frequency_offsets: dict[str, str] = {
    "Hourly": "h",
    "Calendar day": "D",
    "Weekly": "W",
    "Month end": "ME",
    "Quarter end": "QE",
    "Yearly": "YE",
}

# Dimension-name keywords that imply a downward-positive (depth/pressure) axis.
_DOWNWARD_KEYWORDS = ("depth", "pressure", "pres")


def _first_var(var) -> str:
    """Normalise a variable argument that may arrive as a single-item list."""
    return var[0] if isinstance(var, list) else var


def _datetime_coords(ds: xr.Dataset) -> list[str]:
    return [
        name for name in ds.coords
        if np.issubdtype(ds.coords[name].dtype, np.datetime64)
    ]


def _resolve_title(ds: xr.Dataset, var: str, title: str | None) -> str:
    if title:
        return title
    return ds[var].attrs.get("long_name", var)


def plot(
    var,
    ds: xr.Dataset,
    dimension: str,
    *,
    title: str | None = None,
    frequency: str | None = None,
    monotonic: bool | None = None,
    featureType: str | None = None,
    invert_yaxis: bool = False,
    swap_axes: bool = False,
):
    """Build the main line plot for *var* against *dimension*.

    Branches on ``featureType``:
    - ``timeseries``: a line vs. time, optionally resampled to *frequency* when
      the time axis is monotonic.
    - everything else (profile / timeSeriesProfile): a line vs. the selected
      dimension, with the y-axis inverted for depth/pressure-style axes.

    Missing values equal to :data:`FILL_VALUE` are masked out before plotting.

    Note: ``widget_location='top'`` is relied upon elsewhere — callers detect
    the slider vs. canvas by index, so do not change it.
    """
    var = _first_var(var)
    title = _resolve_title(ds, var, title)
    masked = ds[var].where(ds[var] != FILL_VALUE)

    if featureType == "timeseries":
        axis_arguments = {
            "grid": True,
            "x": dimension,
            "title": title,
            "responsive": True,
            "widget_location": "top",
            "min_height": 600,
        }
        if monotonic and frequency and frequency != "--":
            time_coords = _datetime_coords(ds)
            resampling = {time_coords[0]: pandas_frequency_offsets[frequency]}
            plot_widget = masked.resample(**resampling).mean().hvplot.line(**axis_arguments)
        else:
            plot_widget = masked.hvplot.line(**axis_arguments)
        if len(list(plot_widget)) >= 2:
            plot_widget[0].height = 90
        return plot_widget

    # --- profile / timeSeriesProfile ---------------------------------------
    axis_arguments = {
        "grid": True,
        "x": dimension,
        "title": title,
        "responsive": True,
        "widget_location": "top",
    }

    invert = _should_invert_yaxis(ds, var, dimension) or invert_yaxis

    # For DSG-style datasets the selected dimension may be a separate 1-D
    # variable (depth, pressure) that shares the observation dimension with
    # `var` but is not registered as a coordinate of it. In that case a
    # DataArray-level `.hvplot.line(x=dimension)` raises KeyError, so fall back
    # to a Dataset-level call exposing both arrays.
    dim_on_var = dimension in ds[var].dims or dimension in ds[var].coords
    try:
        if dim_on_var:
            plot_widget = masked.hvplot.line(**axis_arguments)
        else:
            sub = ds[[v for v in (var, dimension) if v in ds.data_vars]]
            plot_widget = sub.hvplot.line(
                x=dimension,
                y=var,
                **{k: v for k, v in axis_arguments.items() if k != "x"},
            )
        if invert:
            plot_widget[-1].object.opts(invert_yaxis=True)
        if swap_axes:
            plot_widget[-1].object.opts(invert_axes=True)
    except Exception as exc:
        print(f"plot() failed (var={var!r}, dimension={dimension!r}): {exc} — falling back to default axis")
        axis_arguments.pop("x", None)
        plot_widget = masked.hvplot.line(**axis_arguments)

    plot_widget[0].height = 60
    return plot_widget


def _should_invert_yaxis(ds: xr.Dataset, var: str, dimension: str) -> bool:
    """Decide whether a profile plot's y-axis should increase downward.

    True when the dimension name looks like depth/pressure, or when the CF
    ``positive: down`` attribute is set on the dimension or the variable.
    """
    if any(kw in dimension.lower() for kw in _DOWNWARD_KEYWORDS):
        return True
    if dimension in ds and ds[dimension].attrs.get("positive", "") == "down":
        return True
    return ds[var].attrs.get("positive", "") == "down"


def plot_quadmesh(variable_name: str, dataset: xr.Dataset, title: str | None = None):
    """Build a QuadMesh (2-D time × depth) plot for a timeSeriesProfile variable.

    Returns ``None`` when the variable does not have both a time and a second
    (value) index to form the mesh.
    """
    da = dataset[variable_name]

    # Classify each index as the time axis or the second ("value") axis.
    axes: dict[str, str] = {}
    for idx_name in da.indexes:
        key = "time" if np.issubdtype(da[idx_name].dtype, np.datetime64) else "value"
        axes[key] = idx_name

    if title is None:
        title = da.attrs.get("long_name", variable_name)

    if "time" not in axes or "value" not in axes:
        print(f"Variable {variable_name} does not have time and value dimensions.")
        return None
    if axes["time"] not in da.dims or axes["value"] not in da.dims:
        print(f"Variable {variable_name} does not have time and value dimensions.")
        return None

    # Use plain numpy arrays: passing 0-d DataArray scalars into np.linspace
    # trips xarray's array-wrapping and raises.
    time = da[axes["time"]].values
    second = da[axes["value"]].values
    values = da.values

    # Build cell edges from coordinate centres.
    time_edges = np.append(
        time[:-1] - (time[1] - time[0]) / 2,
        time[-1] + (time[-1] - time[-2]) / 2,
    )
    second_edges = np.linspace(second[0], second[-1], len(second) + 1)

    return hv.QuadMesh(
        (time_edges, second_edges, values.T),
        kdims=list(da.indexes),
        vdims=[variable_name],
    ).opts(
        cmap="viridis",
        colorbar=True,
        xlabel=dataset[axes["time"]].attrs.get("long_name", axes["time"]),
        ylabel=dataset[axes["value"]].attrs.get("long_name", axes["value"]),
        title=f"QuadMesh Plot for {title}",
        responsive=True,
        tools=["hover"],
        xrotation=45,
    )
