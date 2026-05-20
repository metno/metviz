"""Reusable Panel/Bokeh widget builders: metadata, data-export, and a generic
visibility toggle used by the apps' header buttons.
"""

from __future__ import annotations

import numpy as np
import panel as pn
import xarray as xr
from bokeh.models import Button, Div

from .html import dict_to_html_ul


def show_hide_widget(event=None, widget=None, hide=None, reveal=None) -> None:
    """Toggle the visibility of *widget*, optionally hiding/revealing a peer.

    Designed for Bokeh ``Button.on_click`` via ``functools.partial``. When the
    target becomes hidden, *reveal* (if given) is shown; when the target becomes
    visible, *hide* (if given) is hidden. Falls back to ``event.obj`` /
    ``event.sender`` when *widget* is not supplied.
    """
    target = widget
    if target is None and event is not None:
        target = getattr(event, "obj", None) or getattr(event, "sender", None)
    if target is None:
        return

    target.visible = not target.visible
    if target.visible and hide is not None:
        hide.visible = False
    elif not target.visible and reveal is not None:
        reveal.visible = True


def _datetime_coords(ds: xr.Dataset) -> list[str]:
    return [
        name for name in ds.coords
        if np.issubdtype(ds.coords[name].dtype, np.datetime64)
    ]


def build_download_widget(ds: xr.Dataset, mapping_var_names: dict, has_frequency: bool = True):
    """Build the data-export widget set for a dataset.

    Returns a tuple of:
    ``(export_button, checkbox_group, date_time_range_slider,
    export_options_button, event_log, select_output_format,
    export_resampling_option)``.

    The time-range slider and resampling toggle degrade gracefully to a notice
    ``Div`` when the dataset has no datetime coordinate.
    """
    event_log = Div(text="<br><br><br><br>")

    time_coords = _datetime_coords(ds)
    if time_coords:
        time_dim = time_coords[0]
        time_values = ds.coords[time_dim].values
        date_time_range_slider = pn.widgets.DatetimeRangeSlider(
            name="Date Range",
            start=time_values.min(),
            end=time_values.max(),
            value=(time_values.min(), time_values.max()),
        )
        export_resampling_option = pn.widgets.RadioButtonGroup(
            name="Resampling", options=["Raw", "Resampled"]
        )
    else:
        date_time_range_slider = Div(text="<br><br> Time Dimension not available ")
        export_resampling_option = Div(text="<br><br> Resampling disabled ")

    checkbox_group = pn.FlexBox(
        *[pn.widgets.Checkbox(name=str(name)) for name in mapping_var_names]
    )
    select_output_format = pn.widgets.Select(
        name="Export Format", options=["NetCDF", "CSV", "Parquet"]
    )
    export_button = Button(label="Export", height=30, width=120)
    export_options_button = Button(label="Download", height=30, width_policy="fit")

    if not has_frequency and isinstance(export_resampling_option, pn.widgets.RadioButtonGroup):
        export_resampling_option.visible = False

    return (
        export_button,
        checkbox_group,
        date_time_range_slider,
        export_options_button,
        event_log,
        select_output_format,
        export_resampling_option,
    )


def build_metadata_widget(attrs: dict):
    """Build a hidden metadata ``Div`` and the ``Button`` that toggles it."""
    metadata_layout = Div(
        text=(
            '<font size="2" color="darkslategray"><b>Metadata</b></font>'
            f" {dict_to_html_ul(attrs)}"
        ),
        width=500,
    )
    metadata_layout.visible = False
    metadata_button = Button(label="Metadata", height=30, width=120)
    return metadata_layout, metadata_button
