"""Panel control to manage map overlay layers: order, opacity, visibility.

The app registers each layer it adds (e.g. a WMS overlay) via :meth:`add`. The
manager owns the layer's place in the map's draw stack: ipyleaflet draws layers
in insertion order, so reordering re-adds the managed layers (top of the list =
drawn last = on top). Opacity sets ``layer.opacity``; visibility add/removes the
layer from the map.
"""

from __future__ import annotations

from functools import partial

import panel as pn


class LayerManager:
    """Track and control the overlay layers added to a map.

    Parameters
    ----------
    get_map : callable -> ipyleaflet.Map
        Returns the current map. Called lazily so the manager survives map
        rebuilds (after a rebuild the app should :meth:`clear` it).
    """

    def __init__(self, *, get_map):
        self._get_map = get_map
        self._entries: list[dict] = []  # ordered top->bottom: {layer, name, visible}
        self.rows = pn.Column(sizing_mode="stretch_width")
        self.empty = pn.pane.Markdown("*No layers added yet.*")
        self.layout = pn.Column(
            pn.pane.Markdown("### Layers"), self.empty, self.rows, sizing_mode="stretch_width"
        )
        self._render()

    # --- public API (the UI and the app call these) -------------------------
    def add(self, layer, name: str) -> None:
        """Register *layer* (newest on top) and (re)add it to the map."""
        self._entries.insert(0, {"layer": layer, "name": name, "visible": True})
        self._restack()
        self._render()

    def clear(self) -> None:
        """Forget all layers (e.g. after the map is rebuilt for a new CRS)."""
        self._entries = []
        self._render()

    def remove(self, layer) -> None:
        self._safe_remove(layer)
        self._entries = [e for e in self._entries if e["layer"] is not layer]
        self._render()

    def move(self, layer, delta: int) -> None:
        """Move *layer* up (delta<0) or down (delta>0) in the draw stack."""
        i = self._index(layer)
        j = i + delta
        if i is None or not (0 <= j < len(self._entries)):
            return
        self._entries[i], self._entries[j] = self._entries[j], self._entries[i]
        self._restack()
        self._render()

    def set_opacity(self, layer, value: float) -> None:
        try:
            layer.opacity = value
        except Exception:
            pass

    def set_visible(self, layer, value: bool) -> None:
        entry = self._entries[self._index(layer)]
        entry["visible"] = value
        if value:
            self._restack()
        else:
            self._safe_remove(layer)

    # --- internals ----------------------------------------------------------
    def _index(self, layer):
        for i, e in enumerate(self._entries):
            if e["layer"] is layer:
                return i
        return None

    def _safe_remove(self, layer):
        try:
            self._get_map().remove_layer(layer)
        except Exception:
            pass

    def _restack(self):
        """Re-add visible layers so map draw order matches the list (top first)."""
        m = self._get_map()
        for e in self._entries:
            self._safe_remove(e["layer"])
        # add bottom-to-top so the first list entry ends up drawn last (on top)
        for e in reversed(self._entries):
            if e["visible"]:
                m.add_layer(e["layer"])

    def _render(self):
        self.empty.visible = not self._entries
        self.rows[:] = [self._row(e) for e in self._entries]

    def _row(self, entry):
        layer = entry["layer"]
        visible = pn.widgets.Checkbox(value=entry["visible"], width=24, align="center")
        visible.param.watch(lambda ev, ly=layer: self.set_visible(ly, ev.new), "value")
        opacity = pn.widgets.FloatSlider(
            start=0.0, end=1.0, step=0.05, value=float(getattr(layer, "opacity", 1.0) or 1.0),
            name="", width=120, align="center",
        )
        opacity.param.watch(lambda ev, ly=layer: self.set_opacity(ly, ev.new), "value")
        up = pn.widgets.Button(name="▲", width=34, align="center")
        up.on_click(partial(self._on_move, layer, -1))
        down = pn.widgets.Button(name="▼", width=34, align="center")
        down.on_click(partial(self._on_move, layer, 1))
        remove = pn.widgets.Button(name="✕", width=34, button_type="danger", align="center")
        remove.on_click(partial(self._on_remove, layer))
        label = pn.pane.Markdown(f"**{entry['name']}**", width=140, align="center")
        return pn.Row(visible, label, opacity, up, down, remove, sizing_mode="stretch_width")

    def _on_move(self, layer, delta, event=None):
        self.move(layer, delta)

    def _on_remove(self, layer, event=None):
        self.remove(layer)
