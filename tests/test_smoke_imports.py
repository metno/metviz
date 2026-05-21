"""Smoke test: every importable library module loads cleanly against the real
viz stack (catches missing deps, syntax errors, bad top-level statements).

The app entry points (``TSP/main.py``, ``trj/main.py``) are intentionally
excluded — they execute Panel server setup at import time and require a live
session / network.
"""

import importlib

import pytest

LIBRARY_MODULES = [
    "common",
    "common.urls",
    "common.data",
    "common.variables",
    "common.routing",
    "common.csw",
    "common.html",
    "common.download",
    "common.widgets",
    "common.redirect",
    "common.logging_utils",
    "plotting",
    "utility",  # ncapp feature-type models
]


@pytest.mark.parametrize("module", LIBRARY_MODULES)
def test_module_imports(module):
    assert importlib.import_module(module) is not None
