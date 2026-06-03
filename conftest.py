"""Pytest configuration: make the app source trees importable.

The Panel apps are directory-served, so at runtime ``common`` lives on
``PYTHONPATH`` and ``utility`` is local to each app. We mirror that here by
adding ``metviz`` (for ``import common...`` and ``import plotting``) and
``ncapp/app`` (for ``import utility``) to ``sys.path``.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
for path in (ROOT / "metviz", ROOT / "metviz" / "TSP", ROOT / "ncapp" / "app"):
    sys.path.insert(0, str(path))
