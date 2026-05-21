"""Reusable WMS GetCapabilities loader for Panel + ipyleaflet apps.

:func:`list_layers` fetches a WMS GetCapabilities document and returns its
layers; :class:`WmsLoader` wraps that in a small Panel control (URL box, layer
picker, "add to map" button). The target map and its CRS are supplied lazily,
so the loader keeps working across map rebuilds / projection switches.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import owslib.wms
import panel as pn
from ipyleaflet import WMSLayer, projections

# WMS request-control params that belong to a specific operation (e.g. a
# GetCapabilities link). They must be stripped from the base URL before it is
# handed to a WMSLayer, which appends its own GetMap params.
_WMS_CONTROL_PARAMS = {"service", "request", "version"}


def wms_base_url(url: str) -> str:
    """Strip GetCapabilities/GetMap control params, keeping the service base.

    A catalogue often advertises a WMS as a GetCapabilities URL
    (``…/wms?SERVICE=WMS&REQUEST=GetCapabilities``). Passed straight to a
    WMSLayer that becomes a broken GetMap (``REQUEST=GetCapabilities`` lingers),
    so the server returns XML instead of an image. Drop the control params but
    keep any others (e.g. an access token).
    """
    parts = urlparse(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _WMS_CONTROL_PARAMS]
    return urlunparse(parts._replace(query=urlencode(kept)))


def list_layers(url: str):
    """Fetch a WMS GetCapabilities and return ``(layers, version, title, crs)``.

    *layers* is a list of ``(name, title)`` tuples; *crs* is the sorted set of
    EPSG codes (e.g. ``"EPSG:4326"``) supported across all layers. Raises on
    network/parse failure — the caller is expected to handle the exception.
    """
    wms = owslib.wms.WebMapService(url)
    layers = [(name, getattr(layer, "title", "") or "") for name, layer in wms.contents.items()]
    crs = set()
    for layer in wms.contents.values():
        crs.update(getattr(layer, "crsOptions", None) or [])
    identification = getattr(wms, "identification", None)
    title = (getattr(identification, "title", "") if identification else "") or ""
    return layers, wms.version, title, sorted(crs)


class WmsLoader:
    """Load a WMS GetCapabilities URL, pick layers, and add them to a map.

    Parameters
    ----------
    get_map : callable -> ipyleaflet.Map
        Returns the map to add layers to. Called lazily so the loader survives
        map rebuilds / projection switches.
    get_crs : callable -> crs, optional
        Returns the CRS for added layers (default: the map's current ``crs``,
        else EPSG4326). Used only when *resolve_crs* is not given.
    resolve_crs : callable(str) -> crs | None, optional
        Given the EPSG code the user picked from the CRS dropdown, return the
        ipyleaflet CRS to add the layer with (and switch the map to a matching
        projection as a side effect), or ``None`` if no map supports that CRS.
        When ``None`` is returned the layer is not added and a message is shown.
    on_add : callable(layer, name) -> None, optional
        Called for each built WMS layer instead of adding it to the map
        directly, so a layer manager can own placement/ordering. When omitted,
        the loader adds the layer to the map itself.
    """

    def __init__(self, *, get_map, get_crs=None, resolve_crs=None, on_add=None):
        self._get_map = get_map
        self._get_crs = get_crs
        self._resolve_crs = resolve_crs
        self._on_add = on_add
        self.crs_options: list[str] = []
        self.url_input = pn.widgets.TextInput(name="WMS GetCapabilities URL", placeholder="Enter WMS URL")
        self.load_button = pn.widgets.Button(name="Load capabilities", button_type="success")
        self.error = pn.pane.Alert("", alert_type="danger", visible=False)
        self.layers_md = pn.pane.Markdown("", sizing_mode="stretch_width", visible=False)
        self.layer_select = pn.widgets.CheckBoxGroup(name="Available layers", options=[], visible=False)
        self.crs_select = pn.widgets.Select(name="CRS", options=[], visible=False)
        self.add_button = pn.widgets.Button(name="Add selected layer(s)", button_type="primary", visible=False)
        self.load_button.on_click(self.load)
        self.add_button.on_click(self.add_selected)
        self.layout = pn.Column(
            self.url_input,
            self.load_button,
            self.error,
            self.layers_md,
            self.layer_select,
            self.crs_select,
            self.add_button,
            sizing_mode="stretch_width",
        )

    def _show_error(self, message: str) -> None:
        self.error.object = message
        self.error.visible = True
        self.layers_md.visible = False
        self.layer_select.visible = False
        self.crs_select.visible = False
        self.add_button.visible = False

    def load(self, event=None) -> None:
        """Fetch capabilities for the entered URL and populate the layer picker."""
        url = self.url_input.value.strip()
        if not url:
            self._show_error("Please enter a WMS GetCapabilities URL.")
            return
        try:
            layers, version, title, crs = list_layers(url)
        except Exception as exc:
            self._show_error(f"Error loading WMS: {exc}")
            return
        self.crs_options = crs
        self.error.visible = False
        self.layers_md.object = (
            "### Available layers\n"
            + "\n".join(f"- **{name}**: {ttl}" for name, ttl in layers)
            + f"\n\n*WMS {version}{(' — ' + title) if title else ''}*"
        )
        # options as {label: value} so the checkbox value is the layer name.
        self.layer_select.options = {(f"{name}: {ttl}" if ttl else name): name for name, ttl in layers}
        self.crs_select.options = crs
        self.crs_select.value = "EPSG:4326" if "EPSG:4326" in crs else (crs[0] if crs else None)
        self.layers_md.visible = True
        self.layer_select.visible = True
        self.crs_select.visible = bool(crs)
        self.add_button.visible = True

    def add_selected(self, event=None) -> None:
        """Add the checked layers to the map using the picked CRS.

        With *resolve_crs*, the picked EPSG code decides both the CRS and which
        map projection the layer goes to; an unsupported pick shows a message
        and adds nothing.
        """
        url = self.url_input.value.strip()
        names = self.layer_select.value
        if not url or not names:
            return
        getmap_url = wms_base_url(url)
        if self._resolve_crs is not None:
            chosen = self.crs_select.value
            crs = self._resolve_crs(chosen)
            if crs is None:
                # Keep the pickers visible so the user can choose another CRS.
                self.error.object = (
                    f"No map projection available for {chosen}. "
                    "Pick EPSG:4326, EPSG:3857, or UPS North (EPSG:32661/5041)."
                )
                self.error.visible = True
                return
        else:
            crs = self._get_crs() if self._get_crs is not None else projections.EPSG4326
        self.error.visible = False
        lmap = self._get_map()
        for name in names:
            layer = WMSLayer(
                url=getmap_url, layers=name, name=name, crs=crs, transparent=True, format="image/png"
            )
            if self._on_add is not None:
                self._on_add(layer, name)
            else:
                lmap.add_layer(layer)
