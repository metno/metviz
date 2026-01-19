
import param
import panel as pn

class Javascript(pn.reactive.ReactiveHTML):
    value = param.String(
        default="",
        allow_None=False,
        doc="""Javascript code. When the value is set it will be evaluated in the browser.
        Afterwards the value will be set to ''""",
    )

    def __init__(self):
        super().__init__(height=0, width=0, margin=0)

    def eval(self, value: str):
        self.value = value

    _template = "<div id='pn-container'></div>"
    _scripts = {
        "value": """
        console.log(data.value)
        
        if (data.value!=''){
            eval(data.value)
            data.value=""
        }"""
    }