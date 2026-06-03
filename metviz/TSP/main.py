"""TSP Panel app — interactive plots for timeSeries / profile / timeSeriesProfile
OPeNDAP datasets.

Served as a Panel directory app (``panel serve /TSP``). Two modes:

- No ``url`` session argument: render a landing page with a URL input box and a
  table of example datasets; on submit, detect the featureType and redirect to
  the matching app (``/TSP`` or ``/TRJ``).
- With a ``url``: load the dataset, build the variable/axis/export widgets and
  render the plot.

Generic helpers live in the shared ``common`` package; plotting lives in
``common.plotting``; this module wires the widgets and callbacks together.

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
import threading
import time

import holoviews as hv
import panel as pn
from bokeh.layouts import Spacer, column
from bokeh.models import Button, Div
from common.data import load_data
from common.data_access import build_data_access
from common.logging_utils import create_logger
from common.plotting import plot, plot_quadmesh
from common.urls import validate_opendap, validate_url
from common.variables import (
    get_axis_candidates,
    get_plottable_vars,
    is_empty,
    sort_axis_candidates,
)
from common.widgets import show_hide_widget
from starlette.templating import Jinja2Templates

pn.param.ParamMethod.loading_indicator = True
hv.extension("bokeh")

logger = create_logger(__name__)
logger.info("Starting the application...")

templates = Jinja2Templates(directory="/app/templates")

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


pn.state.onload(callback=lambda: logger.info("server loaded"))
pn.state.on_session_destroyed(callback=lambda ctx: logger.info("session destroyed"))


# ---------------------------------------------------------------------------
# Dashboard (url given) — dataset selection lives in the Search Catalog app.
# ---------------------------------------------------------------------------
if "url" not in pn.state.session_args:
    # No dataset selected: point the user to the Search Catalog app.
    pn.pane.Bokeh(
        column(
            Div(
                text=(
                    "<br><b>No dataset selected.</b><br><br>"
                    "Open the <a href='/Catalog'>Search Catalog</a> to choose a dataset, "
                    "or pass <code>?url=&lt;OPeNDAP URL&gt;</code> in the address."
                )
            )
        )
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

        # `empty_status[name]`: True = confirmed empty, False = has data,
        # None = scan not yet finished. Populated by a background thread.
        empty_status: dict[str, bool | None] = {name: None for name in plottable_vars}
        hide_empty_checkbox = pn.widgets.Checkbox(
            name=f"Hide empty (0/{len(plottable_vars)})", value=False
        )

        def _refresh_var_options() -> None:
            """Recompute the selector's options from `hide_empty_checkbox` + `empty_status`."""
            if hide_empty_checkbox.value:
                visible = [n for n in plottable_vars if empty_status.get(n) is not True]
            else:
                visible = list(plottable_vars)
            new_options = [mapping_var_names[n] for n in visible]
            if list(variables_selector.options) == new_options:
                return
            current = variables_selector.value
            variables_selector.options = new_options
            if current not in new_options and new_options:
                variables_selector.value = new_options[0]

        def _record_empty(name: str, verdict: bool) -> None:
            """Doc-thread callback: record one scan result and refresh the UI."""
            empty_status[name] = verdict
            done = sum(1 for v in empty_status.values() if v is not None)
            total = len(plottable_vars)
            hide_empty_checkbox.name = (
                f"Hide empty ({done}/{total})" if done < total else f"Hide empty ({total}/{total})"
            )
            _refresh_var_options()

        def _on_hide_empty_toggle(event) -> None:
            _refresh_var_options()

        hide_empty_checkbox.param.watch(_on_hide_empty_toggle, parameter_names=["value"])

        # Background scan: read each variable off the request thread and stream
        # results back via `doc.add_next_tick_callback`, which is the only safe
        # way to mutate widget state from a thread on Bokeh's IOLoop.
        _doc = pn.state.curdoc

        def _scan_worker(doc=_doc) -> None:
            t0 = time.time()
            logger.info(f"empty-scan: starting on {len(plottable_vars)} variables")
            empties: list[str] = []
            for name in plottable_vars:
                try:
                    verdict = is_empty(ds, name)
                except Exception as exc:
                    logger.warning(f"is_empty({name!r}) failed: {exc}")
                    verdict = False
                if verdict:
                    empties.append(name)
                if doc is not None:
                    doc.add_next_tick_callback(functools.partial(_record_empty, name, verdict))
            logger.info(
                f"empty-scan: done in {time.time() - t0:.2f}s — "
                f"{len(empties)}/{len(plottable_vars)} empty: {empties}"
            )

        if plottable_vars:
            threading.Thread(target=_scan_worker, daemon=True).start()

        # Resampling only applies to monotonic time series.
        frequency_selector.visible = featureType == "timeseries" and bool(monotonic)

        # Shared Download + Metadata feature: the two header buttons plus the
        # panels they reveal, with the export call wired internally.
        data_access = build_data_access(
            ds,
            url=url,
            variables=mapping_var_names,
            decoded_time=decoded_time,
            loading_target=lambda: main_app,
        )

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
                pn.Column(invert_yaxis_checkbox, swap_axes_checkbox, hide_empty_checkbox),
                pn.Column(data_access.download_button, data_access.metadata_button),
            ),
            quadmesh_checkbox,
            quadmesh_plot,
            plot(initial_var, ds, dimension_group.value, title=variables_selector.value,
                 frequency=frequency_selector.value, monotonic=monotonic, featureType=featureType),
            Spacer(height=10),
            sizing_mode="scale_both",
        )

        main_app = pn.Row(
            plot_container, Spacer(width=10),
            data_access.download_panel, data_access.metadata_panel,
            height_policy="max",
        )
        main_app.servable()
