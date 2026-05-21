"""TSP Panel app — interactive plots for timeSeries / profile / timeSeriesProfile
OPeNDAP datasets.

Served as a Panel directory app (``panel serve /TSP``). Two modes:

- No ``url`` session argument: render a landing page with a URL input box and a
  table of example datasets; on submit, detect the featureType and redirect to
  the matching app (``/TSP`` or ``/TRJ``).
- With a ``url``: load the dataset, build the variable/axis/export widgets and
  render the plot.

Generic helpers live in the shared ``common`` package; plotting lives in
``plotting.py``; this module wires the widgets and callbacks together.

Copyright 2022 MET Norway. Licensed under the Apache License, Version 2.0.
"""

from __future__ import annotations

import os
import sys

# The shared `common` package is mounted at /opt/metviz/common in the container.
# Ensure its parent directory is importable regardless of how PYTHONPATH is set
# (mirrors ncapp's sys.path bootstrap). Override with METVIZ_COMMON_ROOT if the
# deployment mounts it elsewhere.
_COMMON_ROOT = os.environ.get("METVIZ_COMMON_ROOT", "/opt/metviz")
if _COMMON_ROOT not in sys.path:
    sys.path.insert(0, _COMMON_ROOT)

import functools
import json
import time

import holoviews as hv
import pandas as pd
import panel as pn
from bokeh.layouts import Spacer, column
from bokeh.models import Button, Div
from common.data import load_data
from common.download import get_download_link
from common.logging_utils import create_logger
from common.redirect import Redirector
from common.urls import validate_opendap, validate_url
from common.variables import get_axis_candidates, get_plottable_vars, sort_axis_candidates
from common.widgets import build_download_widget, build_metadata_widget, show_hide_widget
from plotting import plot, plot_quadmesh
from starlette.templating import Jinja2Templates

pn.param.ParamMethod.loading_indicator = True
hv.extension("bokeh")

logger = create_logger(__name__)
logger.info("Starting the application...")

templates = Jinja2Templates(directory="/app/templates")

# Example datasets offered on the landing page, grouped by featureType.
EXAMPLE_RESOURCES = {
    "Time Series 1": "https://thredds.met.no/thredds/dodsC/arcticdata/infranor/UiO-Kongsvegen-AWS/UiO-Kongsvegen-AWS-sw200-agg.ncml",
    "Time Series 2": "https://thredds.met.no/thredds/dodsC/arcticdata/obsSynop/01008",
    "Profile 1": "https://opendap1.nodc.no/thredds/dodsC/chemistry/StationM/StationM_2008_2019_v2.nc",
    "Profile 2": "https://opendap1.nodc.no/thredds/dodsC/chemistry/StationM/StationM_2008_2019_v1.nc",
    "Time Series Profile 1": "https://thredds.met.no/thredds/dodsC/arcticdata/frost2netcdf-permafrost/SN99868/SN99868-aggregated.ncml",
    "Time Series Profile 2": "https://thredds.met.no/thredds/dodsC/arcticdata/met.no/obs-temp/obs-temp_20892.nc",
    "Trajectory 1": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/AWS-ITO/aws_2022.nc",
    "Trajectory 2": "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/SIMBA/simba-510_air-temperature2022.nc",
}

# Which Panel app handles each detected featureType.
FEATURE_TYPE_APP = {"timeseries": "TSP", "trajectory": "TRJ", "profile": "TSP"}

# Resampling-frequency labels shown in the UI.
FREQUENCY_OPTIONS = ["--", "Hourly", "Calendar day", "Weekly", "Month end", "Quarter end", "Yearly"]


def _selected_var_name() -> list[str]:
    """Return the internal variable name(s) for the current selector value."""
    label = variables_selector.value
    return [name for name, display in mapping_var_names.items() if display == label]


def _replot() -> None:
    """Rebuild the main plot from the current widget state."""
    with pn.param.set_values(main_app, loading=True):
        plot_container[-2] = plot(
            var=_selected_var_name(),
            ds=ds,
            dimension=dimension_group.value,
            title=variables_selector.value,
            frequency=frequency_selector.value,
            monotonic=monotonic,
            featureType=featureType,
            invert_yaxis=invert_yaxis_checkbox.value,
            swap_axes=swap_axes_checkbox.value,
        )


def _refresh_quadmesh() -> None:
    """Replace the QuadMesh plot with one for the current variable."""
    if quadmesh_plot:
        quadmesh_plot.pop(-1)
    quadmesh_plot.insert(-1, plot_quadmesh(_selected_var_name()[0], ds))


def on_var_select(event) -> None:
    """Rebuild axis candidates for the newly selected variable, then replot."""
    selected = _selected_var_name()
    if not selected:
        return
    options = sort_axis_candidates(ds, get_axis_candidates(ds, selected[0]))
    dimension_group.options = options or ["obs"]
    dimension_group.value = dimension_group.options[0]

    if featureType == "timeseriesprofile" and quadmesh_checkbox is not None:
        quadmesh_checkbox.visible = len(options) >= 2

    _replot()
    logger.info(f"selected variable: {selected}")
    if quadmesh_checkbox is not None and quadmesh_checkbox.value:
        _refresh_quadmesh()


def on_dimension_select(event) -> None:
    _replot()
    logger.info(f"dimension selected: {event.obj.value}")


def on_frequency_select(event) -> None:
    _replot()
    logger.info(f"frequency selected: {event.obj.value}")


def on_invert_yaxis_select(event) -> None:
    _replot()


def on_swap_axes_select(event) -> None:
    _replot()


def on_quadmesh_select(event) -> None:
    """Show/hide the QuadMesh plot in response to the checkbox."""
    with pn.param.set_values(main_app, loading=True):
        if event.obj.value:
            quadmesh_plot.visible = True
            _refresh_quadmesh()
        else:
            quadmesh_plot.visible = False
            if quadmesh_plot:
                quadmesh_plot.pop(-1)
    logger.info(f"quadmesh: {event.obj.value}")


def export_selection(event) -> None:
    """Collect the export selection into a JSON spec and request a download link."""
    format_mapping = {"NetCDF": "nc", "CSV": "csv", "Parquet": "pq"}
    with pn.param.set_values(main_app, loading=True):
        export_format = format_mapping[select_output_format.value]
        fs_active = frequency_selector.visible
        is_resampled = fs_active and frequency_selector.value not in ("--", "Raw")

        if not fs_active or frequency_selector.value == "--":
            time_range: list[str] = []
        else:
            time_range = [str(v) for v in date_time_range_slider.value]

        selected_variables = [cb.name for cb in wbx if cb.value]
        export_dataspec = {
            "url": str(url),
            "variables": selected_variables,
            "decoded_time": decoded_time,
            "time_range": time_range,
            "is_resampled": is_resampled,
            "resampling_frequency": frequency_selector.value if is_resampled else "raw",
            "output_format": export_format,
        }
        download_link = get_download_link(json.dumps(export_dataspec))
        event_log.text = '<marquee behavior="scroll" direction="left"><b>. . .  processing . . .</b></marquee>'
        pn.state.curdoc.add_next_tick_callback(
            functools.partial(_show_download_link, download_link=download_link, output_log=event_log)
        )


def _show_download_link(download_link: str, output_log: Div) -> None:
    """Replace the processing notice with the finished download link."""
    time.sleep(2)
    output_log.text = f'<a href="{download_link}">Download</a>'


pn.state.onload(callback=lambda: logger.info("server loaded"))
pn.state.on_session_destroyed(callback=lambda ctx: logger.info("session destroyed"))


# ---------------------------------------------------------------------------
# Landing page (no url) vs. dashboard (url given)
# ---------------------------------------------------------------------------
if "url" not in pn.state.session_args:
    redirector = Redirector()
    resources_df = pd.DataFrame.from_dict(EXAMPLE_RESOURCES, orient="index", columns=["URL"])
    resources_table = pn.widgets.DataFrame(resources_df, name="Example URLs")
    url_input = pn.widgets.TextInput(name="Data URL", placeholder="Enter data URL...", width=600)
    add_button = pn.widgets.Button(name="Add URL", button_type="primary")
    url_button = pn.widgets.Button(name="Load Data", button_type="primary")

    def add_url(event) -> None:
        """Copy the selected example URL into the input box."""
        selected = resources_table.selection
        if selected:
            url_input.value = resources_df.iloc[selected[0]]["URL"]

    add_button.on_click(add_url)

    @pn.depends(url_button.param.clicks, watch=True)
    def load_data_button(clicks) -> None:
        """Detect the featureType of the entered URL and redirect to its app."""
        url = url_input.value
        _, _, _, _, feature_type = load_data(url)
        logger.info(f"FeatureType detected: {feature_type}")
        target_app = FEATURE_TYPE_APP.get(feature_type, "TSP")
        redirector.redirect(f"/{target_app}?url={url}")

    pn.Column(
        redirector, url_input, url_button, resources_table, add_button,
        sizing_mode="stretch_height",
    ).servable()

else:
    url = pn.state.session_args.get("url")[0].decode("utf8")
    ds = None
    decoded_time = False
    monotonic = None
    featureType = None

    if not (validate_url(url) and validate_opendap(url)):
        pn.pane.Bokeh(
            column(Div(text=f"<br><b>Invalid URL:</b><br>   {url}  <br><br> Please provide a valid OPeNDAP URL."))
        ).servable()
    else:
        logger.info(f"Loading dataset: {url}")
        ds, decoded_time, error_log, monotonic, featureType = load_data(url)
        if ds is None:
            error_html = templates.get_template("error.html").render({"error_traceback": error_log})
            error_div = Div(text=error_html, visible=False)
            error_button = Button(label="", height=50, width=50)
            error_button.on_click(functools.partial(show_hide_widget, widget=error_div))
            pn.pane.Bokeh(
                column(Div(text=f"<b>ValueError</b><br><br> Can't load dataset from {url} "), error_button, error_div)
            ).servable()

    frequency_selector = pn.widgets.Select(options=FREQUENCY_OPTIONS, name="Resampling Frequency")
    frequency_selector.param.watch(on_frequency_select, parameter_names=["value"])

    if ds is not None:
        # Map internal variable name -> display label ("long_name [name]").
        plottable_vars = get_plottable_vars(ds)
        logger.info(f"Identified plottable variables: {plottable_vars}")
        mapping_var_names = {
            name: f"{ds[name].attrs['long_name']} [{name}]" if "long_name" in ds[name].attrs else name
            for name in plottable_vars
        }

        variables_selector = pn.widgets.Select(options=list(mapping_var_names.values()), name="Data Variable")
        initial_var = _selected_var_name()

        axis_options = sort_axis_candidates(ds, get_axis_candidates(ds, initial_var[0])) if initial_var else []
        dimension_group = pn.widgets.RadioBoxGroup(name="Dimension", options=axis_options or ["obs"], inline=False)
        dimension_group.value = dimension_group.options[0]

        if featureType == "timeseriesprofile":
            quadmesh_checkbox = pn.widgets.Checkbox(name="Quadmesh", value=False)
            quadmesh_checkbox.param.watch(on_quadmesh_select, parameter_names=["value"])
            quadmesh_checkbox.visible = len(axis_options) >= 2
        else:
            quadmesh_checkbox = None

        invert_yaxis_checkbox = pn.widgets.Checkbox(name="Invert Y-axis", value=False)
        swap_axes_checkbox = pn.widgets.Checkbox(name="Swap axes", value=False)

        # Resampling only applies to monotonic time series.
        frequency_selector.visible = featureType == "timeseries" and bool(monotonic)

        # Export + metadata widgets.
        (export_button, wbx, date_time_range_slider, export_options_button,
         event_log, select_output_format, export_resampling) = build_download_widget(
            ds, mapping_var_names, has_frequency=True
        )
        export_options_button.on_click(export_selection)

        download_header = Div(
            text='<font size="2" color="darkslategray"><b>Data Export</b></font> <br> Variable Selection'
        )
        metadata_layout, metadata_button = build_metadata_widget(ds.attrs)
        downloader = pn.Row(
            Spacer(width=10),
            pn.Column(
                Spacer(height=120), download_header, wbx, date_time_range_slider,
                select_output_format, export_resampling, export_options_button, event_log,
                width=400, sizing_mode="fixed",
            ),
        )
        downloader.visible = False
        metadata_button.on_click(functools.partial(show_hide_widget, widget=metadata_layout, hide=downloader))
        export_button.on_click(functools.partial(show_hide_widget, widget=downloader, hide=metadata_layout))

        variables_selector.param.watch(on_var_select, parameter_names=["value"])
        dimension_group.param.watch(on_dimension_select, parameter_names=["value"])
        invert_yaxis_checkbox.param.watch(on_invert_yaxis_select, parameter_names=["value"])
        swap_axes_checkbox.param.watch(on_swap_axes_select, parameter_names=["value"])

        logger.info(f"Initial variable: {initial_var}, dimension: {dimension_group.value}")

        quadmesh_plot = pn.Row(sizing_mode="scale_both")
        quadmesh_plot.visible = False
        plot_container = pn.Column(
            pn.Row(
                variables_selector,
                pn.Row(Div(text='<font size="2" color="darkslategray">Dimension</font>'), dimension_group),
                frequency_selector,
                pn.Column(invert_yaxis_checkbox, swap_axes_checkbox),
                pn.Column(export_button, metadata_button),
            ),
            quadmesh_checkbox,
            quadmesh_plot,
            plot(initial_var, ds, dimension_group.value, title=variables_selector.value,
                 frequency=frequency_selector.value, monotonic=monotonic, featureType=featureType),
            Spacer(height=10),
            sizing_mode="scale_both",
        )

        main_app = pn.Row(plot_container, Spacer(width=10), downloader, metadata_layout, height_policy="max")
        main_app.servable()
