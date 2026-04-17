import param
import panel as pn


class Redirector(pn.reactive.ReactiveHTML):
    """Safe client-side redirect helper.

    Set `url` to an absolute or relative URL to navigate the browser there.
    Uses `window.location.assign()` directly — no eval(), no code injection.
    The value is reset to '' after the redirect fires so the component can
    be reused.
    """

    url = param.String(
        default="",
        allow_None=False,
        doc="Target URL. Setting this triggers a client-side redirect.",
    )

    def __init__(self):
        super().__init__(height=0, width=0, margin=0)

    def redirect(self, target_url: str):
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
