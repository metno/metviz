"""Interactive trajectory visualization using Holoviews + ipyleaflet.

This module builds a Panel layout with widgets that allow selecting a
variable and time index from a sample dataset and shows a plot together
with the corresponding location on an ipyleaflet map.
"""

from typing import Tuple

import holoviews as hv
import panel as pn
import xarray as xr
from ipyleaflet import Map, Marker, Polyline, WMSLayer
from bokeh.models import HoverTool, CustomJSHover

pn.extension("ipywidgets", sizing_mode="stretch_width")
hv.extension("bokeh")

# Small set of example remote datasets. Keep uppercase for constants.
RESOURCES = {
    "a": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/AWS-ITO/aws_2022.nc",
    "b": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/SIMBA/simba-510_air-temperature2022.nc",
    "c": "https://thredds.niva.no/thredds/dodsC/datasets/norsoop/color_fantasy/merged_acdd_color_fantasy.nc",
    "d": "https://thredds.niva.no/thredds/dodsC/datasets/nrt/color_fantasy.nc",
}

@pn.cache
def _open_dataset(url: str) -> xr.Dataset:
    """Open an xarray dataset from `url` and raise a clear error if it fails."""
    try:
        return xr.open_dataset(url)
    except Exception as exc:
        raise RuntimeError(f"Failed to open dataset {url!r}: {exc}")


# Load an example dataset (small dataset chosen for faster interactivity).
ds = _open_dataset(RESOURCES["a"])

# Identify plottable variables: at least one dimension and the leading dim is present.
plottable_vars = [
    name
    for name in ds.data_vars
    if getattr(ds[name], "ndim", 0) >= 1 and ds[name].dims[0] in ds.dims
]

# Simple safety check for widgets initialization
if not plottable_vars:
    raise RuntimeError("No plottable variables found in the dataset.")


# Widgets
var_select = pn.widgets.Select(
    name="Data Variable", options=plottable_vars, value=plottable_vars[0]
)

datetime_slider = pn.widgets.DatetimeSlider(
    name="Datetime Slider",
    start=ds.indexes["time"][0],
    end=ds.indexes["time"][-1],
    value=ds.indexes["time"][0],
)

index_value = pn.widgets.TextInput(name="Location", value="index")

# Checkbox to allow choosing whether to use the throttled slider value
# (updates only on mouse-up) or the immediate slider value (updates
# continuously while dragging). Default to throttled to keep UI snappy.
throttle_checkbox = pn.widgets.Checkbox(
    name="Use throttled slider (mouse-up only)", value=False
)


# Custom CRS for the northern polar stereographic projection used by the WMS.
gebco_polar_stereo_north_crs = {
    "name": "EPSG:3996",
    "custom": True,
    "proj4def": "+proj=stere +lat_0=90 +lat_ts=75 +lon_0=0 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs +type=crs",
    "origin": [0.0, -1935824.39],
    "bounds": [[-3333793.82, -3368075.98], [3333793.82, 3368075.98]],
    "resolutions": [16384.0, 8192.0, 4096.0, 2048.0, 1024.0, 512.0, 256.0],
}


gebco_polar_stereo_north_wms = WMSLayer(
    url=(
        "https://wms.gebco.net/2024/north-polar/mapserv?request=getcapabilities&service=wms&version=1.3.0"
    ),
    layers="GEBCO_NORTH_POLAR_VIEW_ICE_2024",
    format="image/png",
    transparent=True,
    min_zoom=0,
    attribution="GEBCO",
    crs=gebco_polar_stereo_north_crs,
)


# Build a simple line connecting all lat/lon points in the dataset for context.
locations = [[float(lat), float(lon)] for lat, lon in zip(ds.latitude.values, ds.longitude.values)]
line = Polyline(locations=locations, color="green", fill=False)


# Create the map and add the trajectory line. Center on the mean location.
m = Map(
    center=(float(ds.latitude.mean().values), float(ds.longitude.mean().values)),
    zoom=0,
    crs=gebco_polar_stereo_north_crs,
    basemap=gebco_polar_stereo_north_wms,
)
m.add(line)

# Attach a private attribute to hold the active marker, avoiding globals.
m._marker = None


# method to convert integer time index to datetime
def index_to_datetime(idx: int) -> pn.widgets.DatetimeSlider:
    """Convert integer time index `idx` to a datetime value from `ds.time`."""
    try:
        return ds.indexes["time"][idx]
    except Exception:
        return ds.indexes["time"][0]
    

def makeplot(variable: str, idx) -> hv.Overlay:
    """Build the Holoviews plot for `variable` at datetime `idx` and update the map.

    Parameters
    - variable: name of the data variable in `ds` to plot
    - idx: a datetime-like object that matches entries in `ds.time`

    Returns a Holoviews overlay (curve + vertical line indicating the selected index).
    """

    vline = hv.VLine(idx).opts(color="red", line_width=2.0, responsive=True)

    # Determine axis labels from dataset attributes when available.
    # Prefer `long_name` and include `units` when present, e.g. "Temperature (K)".
    # X axis: time coordinate
    try:
        time_da = ds["time"]
        time_long = time_da.attrs.get("long_name") if hasattr(time_da, "attrs") else None
        time_units = time_da.attrs.get("units") if hasattr(time_da, "attrs") else None
    except Exception:
        time_long = None
        time_units = None

    xlabel = time_long or "Time"
    if time_units:
        xlabel = f"{xlabel} ({time_units})"

    # Y axis: selected variable
    y_da = ds[variable]
    y_long = y_da.attrs.get("long_name") if hasattr(y_da, "attrs") else None
    y_units = y_da.attrs.get("units") if hasattr(y_da, "attrs") else None
    ylabel = y_long or variable
    if y_units:
        ylabel = f"{ylabel} ({y_units})"

    # Build hover tooltips including the actual variable value ($y).
    # We include the variable's display name and units when available.
    y_name = y_long or variable
    y_unit_text = f" {y_units}" if y_units else ""

    TOOLTIPS = f"""
    <div>
      <div><strong>Time</strong></div>
      <div><span style='font-size:12px'>$x{{%F}}</span></div>
      <div><strong>{y_name}</strong></div>
      <div><span style='font-size:12px'>$y{y_unit_text}</span></div>
    </div>
    """

    hover = HoverTool(
        tooltips=[
            ( 'time',   '@time{%F}'            ),
            ( variable,  f'@{{{variable}}}{{%0.2f}}' ), # use @{ } for field names with spaces
        ],

        formatters={
            '@time'        : 'datetime', # use 'datetime' formatter for '@date' field
            f'@{{{variable}}}' : 'printf',   # use 'printf' formatter for '@{adj close}' field
                                        # use default 'numeral' formatter for other fields
        },

        # display a tooltip whenever the cursor is vertically in line with a glyph
        mode='vline',
    )

    # Curve for the selected variable. Enable a grid for easier reading
    # of the curve values. Also set axis labels using the discovered
    # `long_name` and `units`.
    fig = hv.Curve(ds[variable]).opts(
        # hover_tooltips=TOOLTIPS,
        fontsize=12,
        framewise=True,
        responsive=True,
        show_grid=True,
        xlabel=xlabel,
        ylabel=ylabel,
        tools=[hover],
    )

    # Find nearest time index and move the map marker there
    indexer = ds.indexes["time"].get_indexer([idx], method="nearest")
    pos = int(indexer[0]) if len(indexer) and indexer[0] >= 0 else 0

    center_lat = float(ds["latitude"].isel(time=pos).values)
    center_lon = float(ds["longitude"].isel(time=pos).values)
    center: Tuple[float, float] = (center_lat, center_lon)

    # Update the text input with the current center
    index_value.value = f"{center}"

    # Remove previous marker (if any) and add a new one at the selected time
    if getattr(m, "_marker", None) is not None:
        try:
            m.remove(m._marker)
        except Exception:
            # ignore removal errors; we'll replace marker below
            pass

    try:
        marker = Marker(location=center, draggable=False)
        m.add(marker)
        m._marker = marker
        m.center = center
    except Exception as e:
        index_value.value = f"Marker error: {e}"

    # Return the combined Holoviews object
    return fig * vline

# Bind the function to the widgets and create a dynamic map.
# Helper bound function that selects the slider value source depending on
# the checkbox. It returns `datetime_slider.value_throttled` when the
# checkbox is True, otherwise `datetime_slider.value` for immediate updates.
# We bind the helper so it's reactive to the checkbox and both slider values.
get_idx = pn.bind(
    lambda use_throttled, vt, v: vt if use_throttled else v,
    throttle_checkbox,
    datetime_slider.param.value_throttled,
    datetime_slider.param.value,
)

# Now bind `makeplot` to the variable selector and the resolved index value.
bound_function = pn.bind(makeplot, variable=var_select, idx=get_idx)
dmap = hv.DynamicMap(bound_function)


# Compose the layout: widgets on top, then the plot and map together
layout = pn.Column(
    pn.Row(var_select, datetime_slider, throttle_checkbox),
    index_value,
    pn.Column(dmap, m, sizing_mode="scale_both"),
)


# Make the layout servable in a Panel server or notebook
layout.servable()