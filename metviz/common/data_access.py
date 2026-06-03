"""Shared "data access" feature: the **Download** and **Metadata** header
buttons plus the panels they reveal, with the export fully wired.

Both Panel apps (``TSP`` and ``trj``) want the same thing next to their plot:

  * a **Download** button that reveals a panel for picking variables, a time
    range, an output format and a resampling frequency, then requests a
    time-limited download link from the processing service; and
  * a **Metadata** button that reveals the dataset's global attributes.

The orchestration (assembling the export spec, calling
:func:`common.download.get_download_link`, toggling the two panels) used to be
copy-pasted into each app's ``main.py``. It now lives here: an app calls
:func:`build_data_access` once, drops the two buttons in its header and the two
panels in its layout, and is done.

Low-level widget construction (and the time-axis degradation when a dataset has
no datetime coordinate) stays in :mod:`common.widgets`; this module is the
higher-level glue that wires them to the export call.
"""

from __future__ import annotations

import functools
import json
from contextlib import nullcontext
from dataclasses import dataclass

import panel as pn
from bokeh.models import Button, Div

from .download import get_download_link
from .widgets import build_download_widget, build_metadata_widget, show_hide_widget

# Resampling-frequency labels offered in the download panel. "--" means "do not
# resample"; the rest map to pandas offsets in ``common.dataprep`` (server side).
FREQUENCY_OPTIONS = ["--", "Hourly", "Calendar day", "Weekly", "Month end", "Quarter end", "Yearly"]

# UI export-format label -> server ``output_format`` token.
_FORMAT_MAPPING = {"NetCDF": "nc", "CSV": "csv", "Parquet": "pq"}

# Frequency values that mean "no resampling".
_RAW_FREQUENCIES = {"--", "Raw", "raw"}


@dataclass
class DataAccessPanel:
    """The pieces an app places into its own layout.

    ``download_button`` / ``metadata_button`` go in the app header; clicking
    either reveals its panel and hides the other. ``download_panel`` and
    ``metadata_panel`` are hidden by default and go wherever the app wants the
    revealed content to appear.
    """

    download_button: Button
    metadata_button: Button
    download_panel: pn.Column
    metadata_panel: Div


def build_data_access(
    ds,
    *,
    url: str,
    variables: list[str] | dict | None = None,
    decoded_time: bool = True,
    loading_target=None,
) -> DataAccessPanel:
    """Build the wired Download + Metadata feature for *ds* served from *url*.

    Parameters
    ----------
    ds:
        The open dataset (used for its time axis and global attributes).
    url:
        OPeNDAP URL of the dataset; sent verbatim in the export spec.
    variables:
        Variable names to offer as export checkboxes. Accepts a list, or a
        ``{name: label}`` mapping (only the keys/names are used). Defaults to
        every data variable in *ds*.
    decoded_time:
        Whether the dataset's time axis was CF-decoded; forwarded to the worker.
    loading_target:
        Optional Panel object to flag ``loading=True`` on while the export
        request is in flight (typically the app's main container). May also be a
        zero-argument callable returning that object, for apps that build their
        container *after* this component (resolved at click time).
    """
    if variables is None:
        names = list(ds.data_vars)
    elif isinstance(variables, dict):
        names = list(variables)
    else:
        names = list(variables)
    # build_download_widget keys its checkboxes off the mapping's names.
    name_map = {name: name for name in names}

    (
        download_button,
        checkbox_group,
        time_range_slider,
        export_button,
        event_log,
        format_select,
        _resampling_toggle,  # superseded by the frequency selector below
    ) = build_download_widget(ds, name_map, has_frequency=True)

    # Clarify the labels for the two-button header convention.
    download_button.label = "Download"
    export_button.label = "Get download link"

    # A self-contained resampling control (TRJ has no plot-side frequency
    # selector to borrow). Only meaningful when there is a time axis to resample
    # on — `build_download_widget` returns a notice Div for the slider in that
    # case, which we detect to decide whether to show the selector.
    has_time = isinstance(time_range_slider, pn.widgets.DatetimeRangeSlider)
    frequency_select = pn.widgets.Select(
        name="Resampling frequency", options=FREQUENCY_OPTIONS, value="--"
    )
    frequency_select.visible = has_time

    download_panel = pn.Column(
        Div(text='<font size="2" color="darkslategray"><b>Data Export</b></font><br>Variable selection'),
        checkbox_group,
        time_range_slider,
        format_select,
        frequency_select,
        export_button,
        event_log,
        width=400,
        sizing_mode="fixed",
    )
    download_panel.visible = False

    metadata_panel, metadata_button = build_metadata_widget(ds.attrs)

    export_button.on_click(
        functools.partial(
            _request_download,
            url=url,
            decoded_time=decoded_time,
            checkbox_group=checkbox_group,
            time_range_slider=time_range_slider,
            format_select=format_select,
            frequency_select=frequency_select,
            event_log=event_log,
            loading_target=loading_target,
        )
    )

    # Header buttons: each reveals its own panel and hides the peer.
    download_button.on_click(
        functools.partial(show_hide_widget, widget=download_panel, hide=metadata_panel)
    )
    metadata_button.on_click(
        functools.partial(show_hide_widget, widget=metadata_panel, hide=download_panel)
    )

    return DataAccessPanel(
        download_button=download_button,
        metadata_button=metadata_button,
        download_panel=download_panel,
        metadata_panel=metadata_panel,
    )


def _request_download(
    event=None,
    *,
    url: str,
    decoded_time: bool,
    checkbox_group,
    time_range_slider,
    format_select,
    frequency_select,
    event_log: Div,
    loading_target,
) -> None:
    """Assemble the export spec from the panel widgets and request a link."""
    target = loading_target() if callable(loading_target) else loading_target
    context = pn.param.set_values(target, loading=True) if target is not None else nullcontext()
    with context:
        frequency = getattr(frequency_select, "value", "--")
        is_resampled = frequency not in _RAW_FREQUENCIES

        # Only send a time range when there is a real datetime slider to read.
        if isinstance(time_range_slider, pn.widgets.DatetimeRangeSlider):
            time_range = [str(v) for v in time_range_slider.value]
        else:
            time_range = []

        spec = {
            "url": str(url),
            "variables": [cb.name for cb in checkbox_group if cb.value],
            "decoded_time": decoded_time,
            "time_range": time_range,
            "is_resampled": is_resampled,
            "resampling_frequency": frequency if is_resampled else "raw",
            "output_format": _FORMAT_MAPPING.get(format_select.value, "nc"),
        }

        try:
            link = get_download_link(json.dumps(spec))
        except Exception as exc:  # surface failures in the UI rather than swallow them
            event_log.text = f'<span style="color:#b00">Download request failed: {exc}</span>'
            return

        event_log.text = f'<a href="{link}" target="_blank" rel="noopener"><b>Download your file</b></a>'
