"""Reusable WMS GetCapabilities loader for Panel + ipyleaflet apps.

:func:`list_layers` fetches a WMS GetCapabilities document and returns its
layers; :class:`WmsLoader` wraps that in a small Panel control (URL box, layer
picker, "add to map" button). The target map and its CRS are supplied lazily,
so the loader keeps working across map rebuilds / projection switches.
"""

from __future__ import annotations

import owslib.wms
import panel as pn
from ipyleaflet import WMSLayer, projections


def list_layers(url: str):
    """Fetch a WMS GetCapabilities and return ``(layers, version, title)``.

    *layers* is a list of ``(name, title)`` tuples. Raises on network/parse
    failure — the caller is expected to handle the exception.
    """
    wms = owslib.wms.WebMapService(url)
    layers = [(name, getattr(layer, "title", "") or "") for name, layer in wms.contents.items()]
    identification = getattr(wms, "identification", None)
    title = (getattr(identification, "title", "") if identification else "") or ""
    return layers, wms.version, title


class WmsLoader:
    """Load a WMS GetCapabilities URL, pick layers, and add them to a map.

    Parameters
    ----------
    get_map : callable -> ipyleaflet.Map
        Returns the map to add layers to. Called lazily so the loader survives
        map rebuilds / projection switches.
    get_crs : callable -> crs, optional
        Returns the CRS for added layers (default: the map's current ``crs``,
        else EPSG4326). The WMS server must actually support that CRS.
    """

    def __init__(self, *, get_map, get_crs=None):
        self._get_map = get_map
        self._get_crs = get_crs
        self.url_input = pn.widgets.TextInput(name="WMS GetCapabilities URL", placeholder="Enter WMS URL")
        self.load_button = pn.widgets.Button(name="Load capabilities", button_type="success")
        self.error = pn.pane.Alert("", alert_type="danger", visible=False)
        self.layers_md = pn.pane.Markdown("", sizing_mode="stretch_width", visible=False)
        self.layer_select = pn.widgets.CheckBoxGroup(name="Available layers", options=[], visible=False)
        self.add_button = pn.widgets.Button(name="Add selected layer(s)", button_type="primary", visible=False)
        self.load_button.on_click(self.load)
        self.add_button.on_click(self.add_selected)
        self.layout = pn.Column(
            self.url_input,
            self.load_button,
            self.error,
            self.layers_md,
            self.layer_select,
            self.add_button,
            sizing_mode="stretch_width",
        )

    def _show_error(self, message: str) -> None:
        self.error.object = message
        self.error.visible = True
        self.layers_md.visible = False
        self.layer_select.visible = False
        self.add_button.visible = False

    def load(self, event=None) -> None:
        """Fetch capabilities for the entered URL and populate the layer picker."""
        url = self.url_input.value.strip()
        if not url:
            self._show_error("Please enter a WMS GetCapabilities URL.")
            return
        try:
            layers, version, title = list_layers(url)
        except Exception as exc:
            self._show_error(f"Error loading WMS: {exc}")
            return
        self.error.visible = False
        self.layers_md.object = (
            "### Available layers\n"
            + "\n".join(f"- **{name}**: {ttl}" for name, ttl in layers)
            + f"\n\n*WMS {version}{(' — ' + title) if title else ''}*"
        )
        # options as {label: value} so the checkbox value is the layer name.
        self.layer_select.options = {(f"{name}: {ttl}" if ttl else name): name for name, ttl in layers}
        self.layers_md.visible = True
        self.layer_select.visible = True
        self.add_button.visible = True

    def add_selected(self, event=None) -> None:
        """Add the checked layers to the map using the current CRS."""
        url = self.url_input.value.strip()
        names = self.layer_select.value
        if not url or not names:
            return
        crs = self._get_crs() if self._get_crs is not None else projections.EPSG4326
        lmap = self._get_map()
        for name in names:
            lmap.add_layer(
                WMSLayer(url=url, layers=name, name=name, crs=crs, transparent=True, format="image/png")
            )
