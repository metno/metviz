"""
====================

Copyright 2022 MET Norway

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
"""Interactive map demo used by the ADC NC-CF Data Visualization project.

This module builds a simple ipyleaflet map wrapped in a Panel template and
provides UI widgets for:

- Loading WMS layers by providing a GetCapabilities URL.
- Adding draggable markers to the map and editing marker properties.
- Managing removable layers (markers and WMS layers) via a layer manager.

The UI is assembled using Panel and ipyleaflet and expects the following
optional external dependencies at runtime: `owslib`, `ipywidgets`, and
`ipyleaflet`.

This file is intended for exploratory/demo use and is kept small and
imperative; functions are documented with docstrings to aid maintenance.
"""

import datetime as dt
import os
import sys

# The shared `common` package is mounted at /opt/metviz/common in the container.
# Ensure its parent is importable regardless of PYTHONPATH (see TSP/main.py).
# Override with METVIZ_COMMON_ROOT if the deployment mounts it elsewhere.
_COMMON_ROOT = os.environ.get("METVIZ_COMMON_ROOT", "/opt/metviz")
if _COMMON_ROOT not in sys.path:
    sys.path.insert(0, _COMMON_ROOT)

import holoviews as hv
import pandas as pd
import panel as pn
from bokeh.models import Button
from common.basemap import land_geojson
from common.browser_storage import BrowserStorage
from common.csw import (
    CswRecord,
    build_filter,
    collect_page,
    connect,
    count_hits,
    keep_with_feature_type,
    keep_with_wms,
    parse_bbox,
)
from common.data import load_data
from common.plot_panel import DatasetPlotPanel
from common.trajectory import nearest_index_for_time, track_bounds, track_points
from common.wms import WmsLoader
from ipyleaflet import (
    CircleMarker,
    DrawControl,
    GeoJSON,
    LayersControl,
    Map,
    Marker,
    Polyline,
    TileLayer,
    WMSLayer,
    projections,
)
from ipywidgets import HTML

pn.extension("ipywidgets", "tabulator", sizing_mode="stretch_width")
hv.extension("bokeh")
pn.param.ParamMethod.loading_indicator = True

# Inline plot panel, updated when a search result row is selected.
plot_panel = DatasetPlotPanel()


ACCENT_BASE_COLOR = "#003366"

# --- WMS GetCapabilities loader (reusable component) -------------------------
# Dormant for now (the toggle is hidden); the layer CRS tracks the live map so
# it works across projection switches.
wms_toggle = pn.widgets.Toggle(name="Show WMS Loader", button_type="primary", value=False, visible=False)
wms_loader = WmsLoader(
    get_map=lambda: lmap,
    get_crs=lambda: lmap.crs,
    resolve_crs=lambda epsg: _resolve_wms_crs(epsg),
)
# Shown in the detail card when the search source is WMS (swapped in by
# _on_source_change), so it stays visible; not placed in any layout otherwise.
wms_dialog = wms_loader.layout


def toggle_wms_dialog(event):
    """Toggle visibility of the WMS loader."""
    wms_dialog.visible = wms_toggle.value


wms_toggle.param.watch(toggle_wms_dialog, "value")
# END WMS GetCapabilities loader ---

# CSW Query and Draw Handling (from main.py)

csw_toggle = pn.widgets.Toggle(name="Show CSW Loader", button_type="primary", value=False, visible=False)

csw_url_input = pn.widgets.TextInput(
    name="CSW endpoint URL", placeholder="Enter CSW URL", value="https://nbs.csw.met.no"
)
csw_url_reset_button = pn.widgets.Button(name="Reset CSW URL", button_type="warning", width=120)

# add a button to perform the CSW query
csw_query_button = pn.widgets.Button(name="Query CSW", button_type="success")
# add a button to clear previous results
csw_clear_button = pn.widgets.Button(name="Clear Results", button_type="danger", visible=True)
# DEMO/TEST: inject two known trajectory datasets as fake results so the
# trajectory plot + track overlay can be exercised without the CSW (which does
# not surface featureType). Remove once real trajectory records are available.
csw_demo_button = pn.widgets.Button(name="Demo: trajectories", button_type="default")

# csw_layers_pane = pn.pane.Markdown("", height=100, sizing_mode="stretch_width")
csw_error_pane = pn.pane.Alert("", alert_type="danger", visible=False)
# csw_layers_selector = pn.widgets.CheckBoxGroup(name="Available WMS Layers from CSW search", options=[], visible=False)
csw_add_button = pn.widgets.Button(name="Add Selected Layer(s) to Map", button_type="primary", visible=False)

# datetime pickers for start and end datetime
# set the text color based on theme theme from pn.state.args
# custom_styles = {
#     'background': '#f0f0f0',
#     'border': '2px solid black',
#     'padding': '10px',
#     'input.bk-input-group': {
#         'color': 'black'},
# }

###

# text_input_css = """
# :host(.my-custom-text-input) input.bk-input {
#     color: black;
# }
# """

custom_css = """
/* Target the text input element inside the Panel widget */
:host input.bk-input {
  color: black;
  background: #f0f0f0
}
"""

csw_datetime_picker_start = pn.widgets.DatetimePicker(name="Start DateTime",
                                                      stylesheets=[custom_css]) #,
                                                      #css_classes=['my-custom-text-input'])

# ####



# csw_datetime_picker_start = pn.widgets.DatetimePicker(name="Start DateTime")
csw_datetime_picker_end = pn.widgets.DatetimePicker(name="End DateTime")
csw_datetime_picker_start.placeholder = "Select start datetime"
csw_datetime_picker_end.placeholder = "Select end datetime"
# reset buttons for datetime pickers could be added if needed
csw_datetime_reset_button = pn.widgets.Button(name="Reset DateTime", button_type="warning", width=120)

csw_anytext_input = pn.widgets.TextInput(name="Any Text Search", placeholder="Enter text to search in CSW records")
csw_anytext_reset_button = pn.widgets.Button(name="Reset Any Text", button_type="warning", width=120)

csw_bbox_label = pn.widgets.TextInput(name='BBOX', placeholder='BBOX from drawn shape', value='')
csw_bbox_reset_button = pn.widgets.Button(name="Reset BBOX", button_type="warning", width=120)

csw_output = pn.widgets.TextAreaInput(name='CSW Output', placeholder='CSW Query Output', value='', height=200, sizing_mode="stretch_width")
csw_output.visible = False
csw_output.disabled = True

# --- Search results -> visualize routing ---
# The "link" column holds a small icon linking to the OPeNDAP URL (rendered as
# HTML) so the long URL text doesn't bloat the table; selecting the row plots it.
csw_results_table = pn.widgets.Tabulator(
    pd.DataFrame(columns=["title", "featureType", "link"]),
    name="Results",
    disabled=True,
    selectable=1,
    show_index=False,
    visible=False,
    height=260,
    sizing_mode="stretch_width",
    formatters={"link": {"type": "html"}},
    titles={"link": "", "featureType": "type"},
    widths={"featureType": 110, "link": 44},
)
csw_flyto_button = pn.widgets.Button(name="Fly to on map", disabled=True, visible=False, width=130)

# Pagination: browse the CSW result set 10 at a time so we only probe a page's
# worth of datasets for featureType, not the whole match set.
CSW_PAGE_SIZE = 10

# Refuse any search whose CSW match count exceeds this — the user is asked to
# narrow the query window in space and/or time. A cheap resultType="hits"
# pre-check gets the count before we scan any records.
MAX_HITS = 500
csw_prev_button = pn.widgets.Button(name="◀ Prev", width=90, visible=False)
csw_next_button = pn.widgets.Button(name="Next ▶", width=90, visible=False)
csw_page_label = pn.widgets.StaticText(value="", visible=False)

# Per-session paging state. _csw_pages is a history of computed page dicts so
# Prev is instant; _csw_index points at the page currently shown.
_csw_records: list = []
_csw_state = {"csw": None, "filter": None, "matches": 0}
_csw_pages: list = []
_csw_index = -1

# Map overlays for results: a pin per located record, plus a single highlight
# for the selected one. CircleMarkers keep them out of the layer manager
# (which only tracks Markers / WMSLayers).
_csw_result_markers: list = []
_csw_highlight = None
# Trajectory overlay for the selected record: track polyline + a marker that
# follows taps on the plot. Cleared whenever the selection changes.
_trajectory = {"line": None, "marker": None, "times": None, "points": None}

# --- Remember the last CSW search inputs in the browser (localStorage) ---
# Only the stable fields are persisted. The bbox and datetime range are
# deliberately NOT persisted: stale values silently narrow later searches to
# nothing ("I cleared the text but still get no results").
csw_storage = BrowserStorage(key="metviz_csw_search")
_CSW_FIELDS = {
    "endpoint": csw_url_input,
    "text": csw_anytext_input,
}
_CSW_DATETIME_FIELDS = {"start", "end"}
# Guard so restoring values into widgets does not immediately re-save them.
_csw_restoring = {"flag": False}


def _csw_serialize(name, value):
    """Make a widget value JSON-safe (datetimes -> ISO 8601 strings)."""
    if name in _CSW_DATETIME_FIELDS and value is not None:
        return value.isoformat()
    return value


def _csw_deserialize(name, value):
    """Inverse of :func:`_csw_serialize` (ISO 8601 -> datetime)."""
    if name in _CSW_DATETIME_FIELDS and value:
        try:
            return dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
    return value


def _save_csw_inputs(*events):
    """Persist the current CSW inputs to the browser store."""
    if _csw_restoring["flag"]:
        return
    csw_storage.value = {name: _csw_serialize(name, w.value) for name, w in _CSW_FIELDS.items()}


def _restore_csw_inputs(event):
    """Apply stored CSW inputs to the widgets (on page load / restore)."""
    data = event.new or {}
    _csw_restoring["flag"] = True
    try:
        for name, widget in _CSW_FIELDS.items():
            if name in data:
                widget.value = _csw_deserialize(name, data[name])
    finally:
        _csw_restoring["flag"] = False


for _csw_field in _CSW_FIELDS.values():
    _csw_field.param.watch(_save_csw_inputs, "value")
csw_storage.param.watch(_restore_csw_inputs, "value")


# Source toggle: search for OPeNDAP datasets (plot) or WMS-backed records
# (add as a map layer). Switches both the result filter and the select action.
SOURCE_OPENDAP = "OPeNDAP (plot)"
SOURCE_WMS = "WMS (map layer)"
# Default to WMS to match the default NBS endpoint (which serves WMS, not
# featureType/OPeNDAP records); switch to OPeNDAP for a featureType catalogue.
source_select = pn.widgets.RadioButtonGroup(
    name="Source", options=[SOURCE_OPENDAP, SOURCE_WMS], value=SOURCE_WMS
)


def _wms_mode() -> bool:
    return source_select.value == SOURCE_WMS


# Search inputs go in a collapsible Card (collapsed after a search to save space);
# results live separately so they can sit in their own panel below the map.
search_card = pn.Card(
    csw_storage,
    source_select,
    pn.Row(csw_url_input, csw_url_reset_button),
    pn.Row(csw_anytext_input, csw_anytext_reset_button),
    pn.Row(csw_bbox_label, csw_bbox_reset_button),
    pn.Row(csw_datetime_picker_start, csw_datetime_picker_end, csw_datetime_reset_button),
    pn.Row(csw_query_button, csw_clear_button, csw_demo_button),
    csw_error_pane,
    title="CSW Search",
    collapsible=True,
    collapsed=False,
    sizing_mode="stretch_width",
)

results_panel = pn.Column(
    csw_output,
    csw_results_table,
    pn.Row(csw_prev_button, csw_page_label, csw_next_button),
    csw_flyto_button,
    sizing_mode="stretch_both",
)




def _selected_datetime_range():
    """Return (start, stop) datetimes if both pickers are set, else (None, None)."""
    start = csw_datetime_picker_start.value
    stop = csw_datetime_picker_end.value
    if start and stop:
        return start, stop
    return None, None


def _clear_result_markers():
    """Remove all result pins and the highlight from the map."""
    global _csw_highlight
    for circle in _csw_result_markers:
        try:
            lmap.remove_layer(circle)
        except Exception:
            pass
    _csw_result_markers.clear()
    if _csw_highlight is not None:
        try:
            lmap.remove_layer(_csw_highlight)
        except Exception:
            pass
        _csw_highlight = None


def _clear_trajectory():
    """Remove the trajectory track overlay + marker from the map."""
    for key in ("line", "marker"):
        layer = _trajectory[key]
        if layer is not None:
            try:
                lmap.remove_layer(layer)
            except Exception:
                pass
            _trajectory[key] = None
    _trajectory["times"] = None
    _trajectory["points"] = None


def _draw_trajectory(points, times):
    """Draw a track polyline + marker on the current map and zoom to fit."""
    line = Polyline(locations=points, color="green", fill=False, weight=3)
    lmap.add_layer(line)
    _trajectory["line"] = line
    marker = Marker(location=points[0], draggable=False)
    lmap.add_layer(marker)
    _trajectory["marker"] = marker
    _trajectory["points"] = points
    _trajectory["times"] = times
    bounds = track_bounds(points)
    try:
        if bounds is not None:
            lmap.fit_bounds(bounds)
    except Exception:
        lmap.center = points[len(points) // 2]


def _show_trajectory(ds):
    """Overlay the dataset's track + a marker on the map and zoom to fit."""
    points = track_points(ds)
    if len(points) < 2:
        return
    times = ds["time"].values if "time" in ds.variables else None
    _draw_trajectory(points, times)


def _on_plot_time(x):
    """Move the trajectory marker to the track point nearest the tapped time."""
    times = _trajectory["times"]
    points = _trajectory["points"]
    marker = _trajectory["marker"]
    if times is None or points is None or marker is None:
        return
    idx = nearest_index_for_time(times, x)
    if idx is None or not (0 <= idx < len(points)):
        return
    marker.location = points[idx]


# Tapping a trajectory's time-series plot moves the marker along the track.
plot_panel.set_time_callback(_on_plot_time)


def _select_row(index):
    """Select table row *index* (which in turn highlights the pin)."""
    if 0 <= index < len(_csw_records):
        csw_results_table.selection = [index]


def _on_marker_click(index):
    """Build an ipyleaflet click handler that selects the matching table row."""
    def handler(**kwargs):
        _select_row(index)
    return handler


def _add_result_markers(records):
    """Drop a pin for each record that carries a location (bbox centre).

    Clicking a pin selects the matching table row (the table-selection watcher
    then highlights it) — the table↔map link is bidirectional.
    """
    for index, record in enumerate(records):
        loc = record.location
        if loc is None:
            continue
        circle = CircleMarker(
            location=loc, radius=6, color="#1f77b4",
            fill_color="#1f77b4", fill_opacity=0.7, weight=1,
        )
        try:
            popup = HTML()
            popup.value = f"<b>{record.title}</b><br/>{record.feature_type or ''}"
            circle.popup = popup
        except Exception:
            pass
        circle.on_click(_on_marker_click(index))
        lmap.add_layer(circle)
        _csw_result_markers.append(circle)


def _reset_selection_ui():
    """Reset the Fly-to button to its no-selection state."""
    csw_flyto_button.disabled = True


def _show_results(records):
    """Render the current page's records into the table and onto the map."""
    global _csw_records
    _csw_records = records
    _clear_result_markers()
    _clear_trajectory()
    _reset_selection_ui()
    plot_panel.clear()
    if not records:
        csw_results_table.visible = False
        csw_flyto_button.visible = False
        return
    wms = _wms_mode()
    rows = []
    for r in records:
        url = r.wms_url if wms else r.opendap_url
        rows.append({
            "title": r.title,
            "featureType": r.feature_type or ("WMS" if wms and r.wms_url else ""),
            "link": (
                f'<a href="{url}" target="_blank" rel="noopener" title="Open source URL">🔗</a>'
                if url else ""
            ),
        })
    csw_results_table.value = pd.DataFrame(rows, columns=["title", "featureType", "link"])
    csw_results_table.selection = []
    csw_results_table.visible = True
    csw_flyto_button.visible = True
    _add_result_markers(records)


def _selected_record():
    """Return the CswRecord for the currently-selected table row, or None."""
    selection = csw_results_table.selection
    if not selection:
        return None
    index = selection[0]
    if 0 <= index < len(_csw_records):
        return _csw_records[index]
    return None


def _update_plot(record):
    """Load the selected record's dataset, plot it, and (for trajectories) draw
    its track on the map. Any previous trajectory overlay is cleared first."""
    _clear_trajectory()
    if record is None or not record.opendap_url:
        plot_panel.clear()
        return
    plot_panel.loading = True
    try:
        ds, _decoded, error, monotonic, feature_type = load_data(record.opendap_url)
        if ds is None:
            plot_panel.show_message(f"Could not load dataset.\n\n`{error}`")
            return
        feature = (feature_type or record.feature_type or "").lower()
        plot_panel.set_dataset(ds, feature, monotonic)
        if feature == "trajectory":
            _show_trajectory(ds)
    except Exception as exc:
        plot_panel.show_message(f"Failed to plot dataset: {exc}")
    finally:
        plot_panel.loading = False


def _highlight_selected(record):
    """Show/move the red highlight marker for the selected record's location."""
    global _csw_highlight
    loc = record.location if record is not None else None
    if loc is None:
        csw_flyto_button.disabled = True
        if _csw_highlight is not None:
            try:
                lmap.remove_layer(_csw_highlight)
            except Exception:
                pass
            _csw_highlight = None
        return
    csw_flyto_button.disabled = False
    if _csw_highlight is None:
        _csw_highlight = CircleMarker(
            location=loc, radius=11, color="red",
            fill_color="red", fill_opacity=0.3, weight=2,
        )
        lmap.add_layer(_csw_highlight)
    else:
        _csw_highlight.location = loc
        if _csw_highlight not in lmap.layers:
            lmap.add_layer(_csw_highlight)


def _update_wms(record):
    """Load the selected WMS record's GetCapabilities into the WMS layer picker."""
    _clear_trajectory()
    plot_panel.clear()
    if record is None or not record.wms_url:
        return
    wms_loader.url_input.value = record.wms_url
    wms_loader.load()  # fetch capabilities -> populate the layer picker


def _on_result_select(event):
    """On row selection: highlight on the map, then plot (OPeNDAP) or load the
    WMS layer picker (WMS), depending on the search source."""
    record = _selected_record()
    _highlight_selected(record)
    if _wms_mode():
        _update_wms(record)
    else:
        _update_plot(record)


# Zoom level used when flying to a record (2 levels further out than before).
FLY_TO_ZOOM = 4


def fly_to_selected(event):
    """Centre (fly) the map on the selected record's location."""
    record = _selected_record()
    loc = record.location if record is not None else None
    if loc is None:
        return
    lmap.center = loc
    lmap.zoom = FLY_TO_ZOOM


def _update_pagination(page):
    """Update the page label and Prev/Next buttons for the given *page* dict.

    The label deliberately distinguishes the featureType-bearing records shown
    from the raw catalogue match count: the filtered total is unknown until the
    whole result set has been scanned (``page['end']``).
    """
    n = len(page["records"])
    offset = page["offset"]
    total = _csw_state["matches"]
    scanned = page["next"] - 1
    kind = "WMS records" if _wms_mode() else "datasets with a featureType"
    if n == 0:
        label = f"No {kind} (scanned all {total} catalogue matches)"
    elif page["end"]:
        label = (
            f"Showing {offset + 1}–{offset + n} of {offset + n} {kind} "
            f"(scanned all {total} catalogue matches)"
        )
    else:
        label = (
            f"Showing {offset + 1}–{offset + n} {kind} "
            f"(scanned {scanned} of {total} catalogue matches)"
        )
    csw_page_label.value = label
    csw_page_label.visible = True
    csw_prev_button.visible = True
    csw_next_button.visible = True
    csw_prev_button.disabled = _csw_index <= 0
    # More pages exist if we've already computed later ones, or this page did
    # not exhaust the catalogue result set.
    csw_next_button.disabled = page["end"] and _csw_index >= len(_csw_pages) - 1


def _compute_page(start_cursor, offset):
    """Build a page dict by collecting up to CSW_PAGE_SIZE matching records.

    The keep predicate depends on the search source: featureType (probe) for
    OPeNDAP, WMS-protocol (metadata only) for WMS.
    """
    # WMS: cheap metadata check, scan a bit further to fill a page; OPeNDAP:
    # each keep probes a dataset, so keep the scan tighter.
    keep, cap = (keep_with_wms, 1000) if _wms_mode() else (keep_with_feature_type, 500)
    records, next_cursor, end, matches = collect_page(
        _csw_state["csw"], _csw_state["filter"],
        start_cursor=start_cursor, page_size=CSW_PAGE_SIZE, fetch_size=CSW_PAGE_SIZE,
        keep=keep, max_scan=cap,
    )
    _csw_state["matches"] = matches
    return {"records": records, "start": start_cursor, "next": next_cursor, "end": end, "offset": offset}


def _show_page(index):
    page = _csw_pages[index]
    _show_results(page["records"])
    _update_pagination(page)


def _run_search_from_page1():
    """(Re)load page 1 from the current connection/filter using the current source."""
    global _csw_pages, _csw_index
    try:
        page = _compute_page(1, 0)
    except Exception as exc:
        csw_error_pane.object = f"CSW query failed: {exc}"
        csw_error_pane.visible = True
        csw_output.visible = False
        return
    _csw_pages = [page]
    _csw_index = 0
    csw_output.visible = False
    _show_page(0)


def _build_current_filter():
    """Build the CSW filter from the widgets, with source-specific narrowing.

    WMS records are identified by their OGC:WMS protocol, not their text — and
    not every WMS record contains "WMS" in its metadata — so we filter them
    client-side (keep_with_wms) over the bbox/time-bounded results. Only when
    the WMS search is otherwise *unconstrained* do we add an AnyText "WMS"
    pre-filter, so the default query still returns something without scanning a
    multi-million-record catalogue from the top.
    """
    text = csw_anytext_input.value.strip() or None
    bbox = parse_bbox(csw_bbox_label.value)
    start, stop = _selected_datetime_range()
    require = None
    if _wms_mode() and not (text or bbox or (start and stop)):
        require = ["WMS"]
    return build_filter(text=text, bbox=bbox, start=start, stop=stop, require=require)


def _has_constraint() -> bool:
    """True when the search has any space/time/text constraint set."""
    text = csw_anytext_input.value.strip() or None
    bbox = parse_bbox(csw_bbox_label.value)
    start, stop = _selected_datetime_range()
    return bool(text or bbox or (start and stop))


def process_query(event):
    """Connect to the CSW, build the space/time/text filter, and load page 1.

    For OPeNDAP searches we first require a constraint (an unfiltered scan opens
    every dataset over the network to detect its featureType). For every search
    we then run a cheap ``resultType="hits"`` pre-check and refuse when the
    match count exceeds ``MAX_HITS``, asking the user to narrow the query window
    in space and/or time.

    Args:
        event: Panel click event (ignored; present to wire up as a callback).
    """
    csw_error_pane.visible = False
    csw_output.value = "Searching catalogue…\n"
    csw_output.visible = True
    endpoint = csw_url_input.value.strip()
    if not endpoint:
        csw_error_pane.object = "Please enter a CSW endpoint URL."
        csw_error_pane.visible = True
        csw_output.visible = False
        return
    if not _wms_mode() and not _has_constraint():
        csw_error_pane.object = (
            "An unfiltered OPeNDAP search opens every dataset over the network "
            "to detect its featureType. Add a text, bounding-box, or time "
            "constraint to narrow the search."
        )
        csw_error_pane.visible = True
        csw_output.visible = False
        return
    try:
        _csw_state["csw"] = connect(endpoint)
        _csw_state["filter"] = _build_current_filter()
        hits = count_hits(_csw_state["csw"], _csw_state["filter"])
        if hits > MAX_HITS:
            csw_error_pane.object = (
                f"This search matches {hits:,} records — too many (limit "
                f"{MAX_HITS}). Reduce the query window in space and/or time "
                "(draw a tighter bounding box or pick a shorter date range)."
            )
            csw_error_pane.visible = True
            csw_output.visible = False
            return
    except Exception as exc:
        csw_error_pane.object = f"CSW query failed: {exc}"
        csw_error_pane.visible = True
        csw_output.visible = False
        return
    _run_search_from_page1()
    # Collapse the search form to make room for the results/detail.
    search_card.collapsed = True


def _on_source_change(event):
    """Swap the detail card (plot vs WMS picker) and re-run the search."""
    detail_pane[:] = [wms_loader.layout if _wms_mode() else plot_panel.layout]
    plot_panel.clear()
    _clear_trajectory()
    if _csw_state["csw"] is not None:
        # Re-running the search under OPeNDAP rules can be expensive, so route
        # through process_query to re-apply the constraint + hits guard.
        process_query(None)


def next_csw_page(event):
    """Show the next page, computing (refilling) it on demand."""
    global _csw_index
    if _csw_index < len(_csw_pages) - 1:
        _csw_index += 1
    else:
        last = _csw_pages[_csw_index]
        if last["end"]:
            return
        _csw_pages.append(_compute_page(last["next"], last["offset"] + len(last["records"])))
        _csw_index += 1
    _show_page(_csw_index)


def prev_csw_page(event):
    """Show the previous (already-computed) page."""
    global _csw_index
    if _csw_index > 0:
        _csw_index -= 1
        _show_page(_csw_index)


# DEMO/TEST: two known trajectory datasets (from the example list).
_DEMO_TRAJECTORIES = [
    ("UiT drifter AWS-ITO (2022)",
     "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/AWS-ITO/aws_2022.nc"),
    ("UiT drifter SIMBA-510 air temperature (2022)",
     "https://thredds.met.no/thredds/dodsC/arcticdata/arctic-passion/UiT-drifters/SIMBA/simba-510_air-temperature2022.nc"),
]


def load_demo_trajectories(event):
    """DEMO/TEST: show the two known trajectory datasets as fake results."""
    global _csw_pages, _csw_index
    records = [
        CswRecord(
            identifier=url,
            title=title,
            references=[{"scheme": "OPeNDAP", "url": url}],
            feature_type="trajectory",
        )
        for title, url in _DEMO_TRAJECTORIES
    ]
    _csw_pages = []
    _csw_index = -1
    csw_page_label.visible = False
    csw_prev_button.visible = False
    csw_next_button.visible = False
    search_card.collapsed = True
    _show_results(records)


csw_query_button.on_click(process_query)
csw_demo_button.on_click(load_demo_trajectories)
csw_next_button.on_click(next_csw_page)
csw_prev_button.on_click(prev_csw_page)
csw_flyto_button.on_click(fly_to_selected)
csw_results_table.param.watch(_on_result_select, "selection")

def clear_csw_results(event):
    """Clear CSW query results, pagination, and reset paging state.

    Args:
        event: Panel click event (ignored; present to wire up as a callback).
    """
    global _csw_records, _csw_pages, _csw_index
    csw_output.value = ""
    csw_output.visible = False
    csw_error_pane.visible = False
    csw_results_table.visible = False
    csw_flyto_button.visible = False
    csw_page_label.visible = False
    csw_prev_button.visible = False
    csw_next_button.visible = False
    _clear_result_markers()
    _clear_trajectory()
    _reset_selection_ui()
    plot_panel.clear()
    _csw_records = []
    _csw_pages = []
    _csw_index = -1
    _csw_state.update(csw=None, filter=None, matches=0)


def reset_csw_endpoint(event):
    """Reset CSW endpoint URL input."""
    csw_url_input.value = ""

csw_url_reset_button.on_click(reset_csw_endpoint)

def reset_csw_anytext(event):
    """Reset CSW Any Text input."""
    csw_anytext_input.value = ""
csw_anytext_reset_button.on_click(reset_csw_anytext)

def reset_csw_datetime(event):
    """Reset CSW DateTime pickers."""
    csw_datetime_picker_start.value = None
    csw_datetime_picker_end.value = None
csw_datetime_reset_button.on_click(reset_csw_datetime)

def reset_csw_bbox(event):
    """Reset CSW BBOX input."""
    csw_bbox_label.value = ""
    # reset the drawn shape on the map if needed
    draw.clear()
csw_bbox_reset_button.on_click(reset_csw_bbox)

def reset_csw_dialog():
    """Reset CSW dialog to initial state."""
    csw_output.value = ""
    csw_output.visible = False
    csw_error_pane.visible = False
    # csw_layers_selector.visible = False
    csw_add_button.visible = False
    # reset other CSW-related widgets if needed
    csw_url_input.value = ""
    csw_anytext_input.value = ""
    csw_bbox_label.value = ""
    csw_datetime_picker_start.value = None
    csw_datetime_picker_end.value = None

csw_clear_button.on_click(clear_csw_results)


def toggle_csw_dialog(event):
    """Toggle visibility of the WMS configuration dialog.

    Args:
        event: Panel widget change event (ignored; used as a watcher callback).
    """
    search_card.visible = csw_toggle.value


csw_toggle.param.watch(toggle_csw_dialog, 'value')



# --- End CSW Query and Draw Handling ---

# --- Map and Marker Management ---

def get_marker_and_map():
    """Create the initial ipyleaflet Map and a main draggable Marker.

    Returns:
        tuple: (marker, lmap) where `marker` is the main Marker instance and
        `lmap` is the ipyleaflet Map instance configured for the demo.
    """
    center = (65.0, 13.0)  # Norway

    lmap = Map(center=center, zoom=4, height=500, scroll_wheel_zoom=True)

    marker = Marker(location=center, draggable=True)
    # Add custom properties
    marker.name = "Main Marker"
    marker.description = "This is a draggable marker."
    lmap.layout.height="100%"
    lmap.layout.width="100%"
    lmap.add_control(LayersControl(position='topright'))
    draw = DrawControl(edit=True,
                       remove=True,
                       circlemarker={},
                       marker={},
                       circle={},
                       polyline={},
                       polygon={},
                       rectangle={"shapeOptions": {}},
                       )
    return marker, lmap, draw

marker, lmap, draw = get_marker_and_map()

# Create styled StaticText widgets that match the theme
coord_styles = {
    'background-color': '#FFFFFF',
    'color': '#FFFFFF',
    'padding': '5px 10px',
    'border-radius': '4px',
    'margin': '0 5px',
    'font-family': 'system-ui, sans-serif',
    'font-size': '18px'
}

lon_label = pn.widgets.StaticText(
    name="Longitude",
    value="",
    styles=coord_styles
)
lat_label = pn.widgets.StaticText(
    name="Latitude",
    value="",
    styles=coord_styles
)

# # Style update function for theme changes
# def update_coord_labels_style(dark_mode=False):
#     new_styles = dict(coord_styles)
#     new_styles.update({
#         'background-color': '#003366' if dark_mode else 'white',
#         'color': 'white' if dark_mode else '#333'
#     })
#     lon_label.styles = new_styles
#     lat_label.styles = new_styles

json_widget = pn.pane.JSON({}, height=75, visible=False)


add_marker_checkbox = pn.widgets.Checkbox(name="Enable Add Marker", value=False, visible=False)

def print_marker_properties(event, marker_obj):
    """Callback invoked when a marker's location changes.

    Updates the `json_widget` pane with the marker's current properties and
    prints the updated values to stdout (useful for debugging in notebooks).

    Args:
        event (dict): Event payload from ipyleaflet containing a 'new'
            key with the new (lat, lon) location.
        marker_obj (Marker): The marker instance whose properties are shown.
    """
    new = event["new"]
    print(f"Marker Name: {marker_obj.name}")
    print(f"Marker Description: {marker_obj.description}")
    print(f"New Location: {new}")
    # Update the json_widget with marker properties
    json_widget.object = {
        "x": new[0],
        "y": new[1],
        "name": marker_obj.name,
        "description": marker_obj.description
    }

# Attach observer to main marker to print and update json_widget when dragged
marker.observe(lambda event, m=marker: print_marker_properties(event, m), 'location')

# Panel widgets for editing marker properties
marker_name_input = pn.widgets.TextInput(name="Marker Name", value="")
marker_desc_input = pn.widgets.TextInput(name="Marker Description", value="")
save_button = pn.widgets.Button(name="Save Marker Properties", button_type="primary")

edit_panel = pn.Column(marker_name_input, marker_desc_input, save_button, visible=False)
current_marker = [None]  # Use a list for mutability in nested scope

def show_edit_panel(marker):
    """Populate the edit panel with the selected marker's properties.

    The edit panel contains text inputs to edit the marker's name and
    description. The selected marker is stored in `current_marker[0]` for
    later saving.

    Args:
        marker (Marker): The marker to edit.
    """
    marker_name_input.value = marker.name if hasattr(marker, "name") else ""
    marker_desc_input.value = marker.description if hasattr(marker, "description") else ""
    edit_panel.visible = True
    current_marker[0] = marker

def save_marker_properties(event):
    """Save edited marker properties back to the marker instance.

    Removes any existing instances of the marker from the map to avoid
    duplication, updates the `name` and `description` attributes, re-adds
    the marker to the map and updates the JSON widget and layer manager.

    Args:
        event: Button click event (ignored; present to wire up as a callback).
    """
    print("current_marker:", current_marker)
    marker = current_marker[0]
    if marker:
        # lmap.remove_layer(current_marker[1])
        # Remove all occurrences to avoid duplicates
        while marker in lmap.layers:
            lmap.remove_layer(marker)
        remove_layer(marker)
        print(f"Removing marker at {marker.location} to update properties.")
        marker.name = marker_name_input.value
        marker.description = marker_desc_input.value
        lmap.add_layer(marker)
        print(f"Saved properties for marker at {marker.location}:")
        print(f"  Name: {marker.name}")
        print(f"  Description: {marker.description}")
        edit_panel.visible = False
        json_widget.object = {
            "x": marker.location[0],
            "y": marker.location[1],
            "name": marker.name,
            "description": marker.description
        }
        marker.popup.value = f"""Hello <b>{marker.description}</b>"""
        update_layer_manager()  # <-- Update if you want to reflect name changes


def create_button_click(val):
    """Simple click handler used for debugging.

    Args:
        val: Value emitted by the widget click (logged to stdout).
    """
    print(val)


save_button.on_click(save_marker_properties)

def on_map_click(**kwargs):
    """Handle clicks on the map to create new markers when enabled.

    If the 'Enable Add Marker' checkbox is checked and the interaction type
    is a 'click', this function will create a new draggable marker at the
    clicked coordinates, attach a popup, register the movement observer,
    and open the edit panel for that marker.

    Args:
        **kwargs: Arbitrary interaction payload from ipyleaflet. Expected keys
            include 'type' and 'coordinates'.
    """
    if add_marker_checkbox.value and kwargs.get("type") == "click":
        latlng = kwargs.get("coordinates")
        if latlng:
            marker = Marker(location=latlng, draggable=True)
            marker.name = f"Marker at {latlng}"
            marker.description = f"Marker at {latlng}"
            lmap.add_layer(marker)
            print(f"Added marker at {latlng}")
            marker.observe(lambda event, m=marker: print_marker_properties(event, m), 'location')
            message = HTML()
            message.placeholder = "Some HTML"
            message.description = "Some HTML"
            message.value = "Hello <b>World</b>"
            marker.popup = message
            show_edit_panel(marker)
            update_layer_manager()  # <-- Only update when a marker is added

def on_mouse_move(**kwargs):
    if kwargs.get("type") == "mousemove":
        coords = kwargs.get("coordinates")
        lon_label.value = f"{coords[1] - 360:.6f}"
        lat_label.value = f"{coords[0]:.6f}"

def on_draw_handler(draw, action, geo_json):
    print("drawing action:", action)
    for i in lmap.layers:
        # Remove a previously drawn shape, but keep the land basemap.
        if isinstance(i, GeoJSON) and getattr(i, "name", "") != LAND_LAYER_NAME:
            lmap.remove_layer(i)
    bounds = geo_json["geometry"]["coordinates"][0]
    # Leaflet can hand back "unwrapped" longitudes (e.g. after panning across
    # the antimeridian, or > 180 in some projections). CRS84 needs lon in
    # [-180, 180], so normalise rather than blindly subtracting 360.
    modified_bounds = [[((lon + 180) % 360) - 180, lat] for lon, lat in bounds]
    ll = modified_bounds[0]
    ur = modified_bounds[2]

    print("bounds:", f"LL: {ll}, UR: {ur}")
    corners = [ll, ur]
    bbox = [item for sublist in corners for item in sublist]
    csw_bbox_label.value = str(bbox)
    GeoJSON(data=geo_json, name="Drawn Shape")
    # this probably already in the map, need to add refresh to the removable layers
    # lmap.add_layer(geo_json_layer)
    pass


lmap.on_interaction(on_map_click)  # Only once!

lmap.on_interaction(on_mouse_move)  # Only once!


draw.on_draw(on_draw_handler)
lmap.add_control(draw)

# component = pn.Column(
#     checkbox,
#     pn.panel(lmap, sizing_mode="stretch_both", min_height=500),
#     pn.Row(json_widget, edit_panel)
# )
####

def get_removable_layers():
    """Return a deduplicated list of layers that can be removed by the UI.

    Excludes the primary `marker` and attempts to ensure uniqueness by a key
    constructed from the layer type and identifying attributes (location and
    name for markers, name for WMS layers).

    Returns:
        list: A list of ipyleaflet layer objects suitable for removal.
    """
    # Exclude the main marker and ensure uniqueness by (location, name)
    seen = set()
    unique_layers = []
    for lyr in lmap.layers:
        if (isinstance(lyr, Marker) and lyr is not marker) or isinstance(lyr, WMSLayer):
            # Use (rounded lat, rounded lon, name) as a unique key
            if isinstance(lyr, Marker):
                key = (round(lyr.location[0], 6), round(lyr.location[1], 6), getattr(lyr, "name", ""))
            elif isinstance(lyr, WMSLayer):
                key = (getattr(lyr, "name", ""),)
            else:
                key = id(lyr)
            if key not in seen:
                unique_layers.append(lyr)
                seen.add(key)
    return unique_layers

def remove_layer(layer):
    """Remove the given layer from the map and refresh the layer manager.

    Repeatedly removes occurrences of the same layer object to handle
    accidental duplicates and then calls `update_layer_manager()` so the
    UI stays in sync.

    Args:
        layer: The ipyleaflet layer object to remove.
    """
    # Remove all occurrences of this layer object (in case of duplicates)
    while layer in lmap.layers:
        lmap.remove_layer(layer)
    update_layer_manager()

def update_layer_manager(**kwargs):
    """Rebuild the layer manager UI to reflect the current removable layers.

    This function queries `get_removable_layers()` and constructs a list of
    rows containing the layer name and a Remove button wired to call
    `remove_layer()` for that layer.
    """
    # Clear and repopulate the layer manager panel
    removable_layers = get_removable_layers()
    items = []
    for lyr in removable_layers:
        lyr_name = getattr(lyr, "name", str(lyr))
        btn = pn.widgets.Button(name="Remove", button_type="danger", width=60)
        # Closure to capture current layer
        btn.on_click(lambda event, layer=lyr: remove_layer(layer))
        items.append(pn.Row(pn.pane.Markdown(f"**{lyr_name}**"), btn))
    layer_manager[:] = items

layer_manager = pn.Column(name="Layer Manager")
update_layer_manager()

# Update the manager whenever a marker or WMS layer is added
def add_marker_and_update(*args, **kwargs):
    """Helper used by external wiring to trigger a layer manager refresh.

    Kept for backwards compatibility with earlier wiring where an add
    operation would explicitly call this helper.
    """
    # on_map_click(*args, **kwargs)
    update_layer_manager()

layer_manager_toggle = pn.widgets.Toggle(name="Show Layer Manager", button_type="primary", value=False, visible=False)


layer_manager_widget = pn.Column(pn.pane.Markdown("### Layers"), layer_manager, visible=False, sizing_mode="stretch_both", max_width=300)

def toggle_layer_manager_dialog(event):
    """Toggle visibility of the WMS configuration dialog.

    Args:
        event: Panel widget change event (ignored; used as a watcher callback).
    """
    layer_manager_widget.visible = layer_manager_toggle.value

layer_manager_toggle.param.watch(toggle_layer_manager_dialog, 'value')

# # Create a toggle for theme switching
# theme_toggle = pn.widgets.Toggle(name='Dark Theme', value=False)

# def on_theme_change(event):
#     """Update coordinate labels style when theme changes"""
#     update_coord_labels_style(event.new)

# theme_toggle.param.watch(on_theme_change, 'value')




# Create toolbar with buttons
toolbar = pn.Row(
    csw_toggle,
    wms_toggle,
    layer_manager_toggle,
    # theme_toggle
)

toolbar.visible = False

# Legacy scaffolding kept defined for the (currently hidden) WMS / marker
# features; not shown in the current layout.
side_opt = pn.Column(edit_panel)
side_opt.visible = True


def show_hide_side_opt_widget(event):
    visible = not side_opt.visible
    side_opt.visible = visible
    toolbar.visible = visible


show_options_button = Button(label="show opt", height=30, width=120, visible=False)
show_options_button.on_click(show_hide_side_opt_widget)


# --- Map projection switch ---------------------------------------------------
# ipyleaflet's CRS is fixed at construction, so switching projection means
# building a fresh Map and re-applying the overlays.
_MERCATOR = "Web Mercator"
_POLAR = "UPS North"
_WGS84 = "WGS84 (lat/lon)"

# UPS North (EPSG:32661) CRS using the canonical GIBS polar tile matrix set, so
# WMS layers picked as UPS North render here. Many polar WMS services (e.g.
# adc-wms.met.no) advertise EPSG:32661/5041 (same projection; the name sets the
# SRS sent to the WMS).
# UPS North has a 2,000,000 m false easting/northing, so the pole sits at
# (2e6, 2e6) and the tile pyramid is centred there (not at the origin). Bounds
# span +/- 9,036,842.76 m around the pole; resolutions halve from full-bounds.
_UPS_FALSE = 2_000_000.0
_UPS_HALF = 9_036_842.7625
_POLAR_CRS = {
    "name": "EPSG:32661",
    "custom": True,
    "proj4def": "+proj=stere +lat_0=90 +lat_ts=90 +lon_0=0 +k=0.994 +x_0=2000000 +y_0=2000000 +datum=WGS84 +units=m +no_defs",
    "origin": [_UPS_FALSE - _UPS_HALF, _UPS_FALSE + _UPS_HALF],
    "bounds": [
        [_UPS_FALSE - _UPS_HALF, _UPS_FALSE - _UPS_HALF],
        [_UPS_FALSE + _UPS_HALF, _UPS_FALSE + _UPS_HALF],
    ],
    "resolutions": [(2 * _UPS_HALF / 256) / (2**z) for z in range(8)],
}


# All three projections open centred on Norway.
NORWAY_CENTER = (65.0, 13.0)
# Land-basemap layer name, also skipped by the draw handler so a drawn bbox
# doesn't remove it.
LAND_LAYER_NAME = "Land"


def _drop_tile_basemaps(m):
    """Remove any tile basemap (e.g. the default OSM, which is Web-Mercator).

    OSM tiles don't render in EPSG:4326 or the polar CRS, so those maps use the
    vector land basemap instead.
    """
    for layer in list(m.layers):
        if isinstance(layer, TileLayer):
            m.remove_layer(layer)


def _add_land(m):
    """Add the vector land basemap (reprojects into the map's CRS)."""
    m.add_layer(
        GeoJSON(
            data=land_geojson(),
            name=LAND_LAYER_NAME,
            style={"color": "#9aa0a6", "weight": 1, "fillColor": "#e9ecef", "fillOpacity": 1.0},
        )
    )


def _make_map(projection):
    """Build a fresh ipyleaflet Map for the given projection (no overlays)."""
    if projection == _POLAR:
        # UPS North has no public tile basemap; use the vector land layer.
        m = Map(center=NORWAY_CENTER, zoom=4, crs=_POLAR_CRS, scroll_wheel_zoom=True)
        _drop_tile_basemaps(m)
        _add_land(m)
    elif projection == _WGS84:
        # EPSG:4326 lat/lon grid. Many polar/national WMS services (e.g.
        # adc-wms.met.no) serve EPSG:4326 but NOT Web Mercator, so a GetMap from
        # a 3857 map fails with HTTP 500; a 4326 map makes those layers render.
        # OSM tiles don't tile in 4326, so use the vector land basemap.
        m = Map(center=NORWAY_CENTER, zoom=4, crs=projections.EPSG4326, scroll_wheel_zoom=True)
        _drop_tile_basemaps(m)
        _add_land(m)
    else:
        m = Map(center=NORWAY_CENTER, zoom=4, scroll_wheel_zoom=True)
    m.layout.height = "100%"
    m.layout.width = "100%"
    m.add_control(LayersControl(position="topright"))
    return m


def _reapply_overlays():
    """Redraw result pins, highlight and trajectory on the (new) map."""
    global _csw_highlight
    _csw_result_markers.clear()
    _csw_highlight = None
    points, times = _trajectory["points"], _trajectory["times"]
    _trajectory["line"] = None
    _trajectory["marker"] = None
    if _csw_records:
        _add_result_markers(_csw_records)
    if points:
        _draw_trajectory(points, times)
    _highlight_selected(_selected_record())


def _rebuild_map(projection):
    """Replace the map with one in *projection*, re-wiring controls + overlays."""
    global lmap, draw
    lmap = _make_map(projection)
    draw = DrawControl(
        edit=True, remove=True, circlemarker={}, marker={}, circle={},
        polyline={}, polygon={}, rectangle={"shapeOptions": {}},
    )
    draw.on_draw(on_draw_handler)
    lmap.add_control(draw)
    lmap.on_interaction(on_mouse_move)
    map_pane.object = lmap
    _reapply_overlays()


# One tab per projection; the single map is shown in the active tab and rebuilt
# in that projection when the tab changes.
_PROJECTIONS = [_MERCATOR, _POLAR, _WGS84]
# EPSG codes each projection tab can render. A WMS layer is added to the tab
# whose codes include the user's picked CRS.
_PROJECTION_EPSG = {
    _MERCATOR: {"EPSG:3857", "EPSG:900913"},
    _POLAR: {"EPSG:5041", "EPSG:32661"},
    _WGS84: {"EPSG:4326", "CRS:84"},
}
_proj_tab_holders = [pn.Column(sizing_mode="stretch_both") for _ in _PROJECTIONS]
projection_tabs = pn.Tabs(
    *zip(_PROJECTIONS, _proj_tab_holders, strict=True), sizing_mode="stretch_both"
)


def _apply_projection(index):
    """Rebuild the map for tab *index* and show it in that tab."""
    _rebuild_map(_PROJECTIONS[index])
    for i, holder in enumerate(_proj_tab_holders):
        holder[:] = [map_pane] if i == index else []


projection_tabs.param.watch(lambda event: _apply_projection(event.new), "active")


def _set_projection(projection):
    """Switch to *projection*'s tab (rebuilding the map) if not already active."""
    index = _PROJECTIONS.index(projection)
    if projection_tabs.active != index:
        projection_tabs.active = index  # fires the watcher -> _apply_projection


# ipyleaflet CRS for each projection tab (must match the map built in _make_map).
_PROJECTION_LEAFLET_CRS = {
    _MERCATOR: projections.EPSG3857,
    _POLAR: _POLAR_CRS,
    _WGS84: projections.EPSG4326,
}


def _resolve_wms_crs(epsg):
    """Map a user-picked WMS CRS to a tab, switch to it, and return its CRS.

    Returns the ipyleaflet CRS for the matching projection tab (switching the
    map to it), or ``None`` if no tab renders *epsg* (caller shows a message).
    """
    code = str(epsg).upper()
    for projection, codes in _PROJECTION_EPSG.items():
        if code in codes:
            _set_projection(projection)
            return _PROJECTION_LEAFLET_CRS[projection]
    return None


# --- Layout: React template (resizable, draggable grid) ----------------------
# Sidebar: collapsible CSW search + the compact results table (same column).
# Main area: map and plot side by side, each a draggable/resizable grid card.
map_pane = pn.panel(lmap, sizing_mode="stretch_both", min_height=380)
# Show the map in the initially-active projection tab.
_proj_tab_holders[projection_tabs.active][:] = [map_pane]
map_card = pn.Card(
    pn.Row(lon_label, lat_label),
    projection_tabs,
    title="Map",
    collapsible=False,
    margin=0,
    sizing_mode="stretch_both",
)
# Detail card content swaps between the inline plot (OPeNDAP) and the WMS layer
# picker (WMS) as the search source changes.
detail_pane = pn.Column(
    wms_loader.layout if _wms_mode() else plot_panel.layout,
    sizing_mode="stretch_both",
)
plot_card = pn.Card(
    detail_pane,
    title="Plot / WMS layers",
    collapsible=False,
    margin=0,
    sizing_mode="stretch_both",
)
source_select.param.watch(_on_source_change, "value")

template = pn.template.ReactTemplate(
    title="OGC Catalogue Explorer",
    sidebar=[search_card, results_panel],
    sidebar_width=440,
)
template.main[0:6, 0:6] = map_card
template.main[0:6, 6:12] = plot_card
template.servable()
