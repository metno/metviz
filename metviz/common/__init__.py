"""Shared utilities for the metviz Panel applications (``TSP`` and ``trj``).

This package holds code that is reused across the directory-served Panel apps:
URL/feature-type validation, dataset loading, plottable-variable discovery,
metadata/download widget builders and a safe client-side redirect helper.

It is made importable inside the container by mounting ``metviz/common`` and
adding its parent directory to ``PYTHONPATH`` (see ``docker-compose.yml``).
App-specific glue (layout, callbacks) stays inside each app directory.
"""
