"""Small helpers to render nested dictionaries (dataset attrs) as HTML."""

from __future__ import annotations

import json
from typing import Any


def _format_value(value: Any, level: int, renderer) -> str:
    if isinstance(value, dict):
        return renderer(value, level + 1)
    if isinstance(value, list):
        return json.dumps(value)
    return str(value)


def dict_to_html(dd: dict, level: int = 0) -> str:
    """Render *dd* as indented ``<br>``-separated bold key/value lines."""
    text = ""
    for key, value in dd.items():
        indent = "&nbsp;" * (4 * level)
        text += f"<br>{indent}<b>{key}</b>: {_format_value(value, level, dict_to_html)}"
    return text


def dict_to_html_ul(dd: dict, level: int = 0) -> str:
    """Render *dd* as nested ``<ul>``/``<li>`` lists."""
    text = "<ul>"
    for key, value in dd.items():
        text += f"<li><b>{key}</b>: {_format_value(value, level, dict_to_html_ul)}</li>"
    return text + "</ul>"
