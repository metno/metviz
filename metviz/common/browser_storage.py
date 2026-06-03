"""Persist a small amount of state in the browser's ``localStorage``.

A client-side ``ReactiveHTML`` helper (same family as :class:`Redirector`):
its :attr:`value` dict is loaded from ``localStorage`` on first render and
written back whenever it changes, so widget state survives a page reload
without any server-side storage.
"""

from __future__ import annotations

import panel as pn
import param


class BrowserStorage(pn.reactive.ReactiveHTML):
    """Two-way sync of the :attr:`value` dict with ``localStorage[key]``.

    Usage: create one, add it to a layout (it is invisible), then watch its
    ``value`` to restore widgets and set its ``value`` to persist them.
    """

    value = param.Dict(default={}, doc="State persisted under `key`.")
    key = param.String(default="metviz", doc="localStorage key.")

    def __init__(self, **params) -> None:
        super().__init__(height=0, width=0, margin=0, **params)

    _template = "<div id='pn-browser-storage'></div>"
    _scripts = {
        # Load once per browser view, guarded by a window-level flag so repeated
        # renders never clobber in-progress edits.
        "render": """
            const guard = '_pn_loaded_' + data.key;
            if (window[guard]) { return }
            window[guard] = true;
            const raw = window.localStorage.getItem(data.key);
            if (raw) {
                try { data.value = JSON.parse(raw); } catch (err) {}
            }
        """,
        # Persist on every change (including the load above — idempotent).
        "value": """
            window.localStorage.setItem(data.key, JSON.stringify(data.value));
        """,
    }
