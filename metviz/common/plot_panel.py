"""A reusable, self-contained Panel component that plots one dataset.

It owns a variable + axis selector and a plot area. Call :meth:`set_dataset`
to (re)point it at a dataset; it renders the first plottable variable and
updates reactively as the user changes the selectors. Used to embed TSP-style
plotting inside other apps (e.g. the OGC_client search results), without the
full TSP dashboard.
"""

from __future__ import annotations

import panel as pn
import xarray as xr

from .plotting import plot
from .variables import get_axis_candidates, get_plottable_vars, sort_axis_candidates


class DatasetPlotPanel:
    """Variable/axis selectors + a plot area for a single xarray Dataset."""

    def __init__(self, *, min_height: int = 400):
        self.variable_select = pn.widgets.Select(name="Variable", options=[], visible=False, width=340)
        self.dimension_select = pn.widgets.Select(name="Axis", options=[], visible=False, width=200)
        self._message = pn.pane.Markdown("Select a record to plot.", sizing_mode="stretch_width")
        self._plot_area = pn.Column(self._message, sizing_mode="stretch_both", min_height=min_height)
        self.layout = pn.Column(
            pn.Row(self.variable_select, self.dimension_select),
            self._plot_area,
            sizing_mode="stretch_both",
        )

        self._ds: xr.Dataset | None = None
        self._feature_type: str | None = None
        self._monotonic: bool | None = None
        self._name_by_label: dict[str, str] = {}
        # Guards programmatic widget updates so we re-plot exactly once.
        self._suppress = False

        self.variable_select.param.watch(self._on_variable, "value")
        self.dimension_select.param.watch(self._on_dimension, "value")

    # --- loading-spinner passthrough -------------------------------------
    @property
    def loading(self) -> bool:
        return self.layout.loading

    @loading.setter
    def loading(self, value: bool) -> None:
        self.layout.loading = value

    # --- public API ------------------------------------------------------
    def show_message(self, text: str) -> None:
        """Show *text* instead of a plot and hide the selectors."""
        self._suppress = True
        try:
            self.variable_select.visible = False
            self.dimension_select.visible = False
        finally:
            self._suppress = False
        self._message.object = text
        self._plot_area[:] = [self._message]

    def clear(self) -> None:
        """Drop the current dataset and show the idle message."""
        self._ds = None
        self.show_message("Select a record to plot.")

    def set_dataset(self, ds: xr.Dataset, feature_type: str | None, monotonic: bool | None) -> None:
        """Point the panel at *ds* and render its first plottable variable."""
        self._ds = ds
        self._feature_type = feature_type
        self._monotonic = monotonic

        names = get_plottable_vars(ds)
        if not names:
            self.show_message("No plottable variables in this dataset.")
            return

        self._name_by_label = {self._label(ds, name): name for name in names}
        labels = list(self._name_by_label)
        self._suppress = True
        try:
            self.variable_select.options = labels
            self.variable_select.value = labels[0]
            self.variable_select.visible = True
            self.dimension_select.visible = True
        finally:
            self._suppress = False
        self._rebuild_axis_and_plot()

    # --- internals -------------------------------------------------------
    @staticmethod
    def _label(ds: xr.Dataset, name: str) -> str:
        long_name = ds[name].attrs.get("long_name")
        return f"{long_name} [{name}]" if long_name else name

    def _current_var(self) -> str | None:
        return self._name_by_label.get(self.variable_select.value)

    def _on_variable(self, event) -> None:
        if not self._suppress:
            self._rebuild_axis_and_plot()

    def _on_dimension(self, event) -> None:
        if not self._suppress:
            self._replot()

    def _rebuild_axis_and_plot(self) -> None:
        if self._ds is None:
            return
        var = self._current_var()
        if var is None:
            return
        options = sort_axis_candidates(self._ds, get_axis_candidates(self._ds, var)) or ["obs"]
        self._suppress = True
        try:
            self.dimension_select.options = options
            self.dimension_select.value = options[0]
        finally:
            self._suppress = False
        self._replot()

    def _replot(self) -> None:
        if self._ds is None:
            return
        var = self._current_var()
        if var is None:
            return
        with pn.param.set_values(self.layout, loading=True):
            try:
                widget = plot(
                    [var], self._ds, self.dimension_select.value,
                    title=self.variable_select.value,
                    monotonic=self._monotonic,
                    featureType=self._feature_type,
                )
                self._plot_area[:] = [widget]
            except Exception as exc:
                self._message.object = f"Could not plot **{var}**: {exc}"
                self._plot_area[:] = [self._message]
