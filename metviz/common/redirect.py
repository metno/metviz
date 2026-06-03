"""Safe client-side redirect component for Panel."""

from __future__ import annotations

import panel as pn
import param


class Redirector(pn.reactive.ReactiveHTML):
    """Trigger a browser navigation from the server side, without ``eval``.

    Set :attr:`url` (via :meth:`redirect`) to an absolute or relative URL and
    the browser navigates there using ``window.location.assign``. The value is
    reset to ``''`` after the redirect fires so the component can be reused.
    """

    url = param.String(
        default="",
        allow_None=False,
        doc="Target URL. Setting this triggers a client-side redirect.",
    )

    def __init__(self) -> None:
        super().__init__(height=0, width=0, margin=0)

    def redirect(self, target_url: str) -> None:
        """Navigate the browser to *target_url*."""
        self.url = target_url

    _template = "<div id='pn-redirector'></div>"
    _scripts = {
        "url": """
        if (data.url !== '') {
            window.location.assign(data.url);
            data.url = '';
        }
        """
    }
