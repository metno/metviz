"""Norwegian land/coastline basemap (mainland, Svalbard, Jan Mayen).

Natural Earth 10m land clipped to the Norway+Svalbard region (EPSG:4326),
bundled with the package. Rendered as a Leaflet GeoJSON vector layer it
reprojects into any map CRS — including UPS North, which has no tile basemap.
"""

from __future__ import annotations

import json
from pathlib import Path

_LAND_PATH = Path(__file__).parent / "norway_svalbard_land.geojson"


def land_geojson() -> dict:
    """Return the Norwegian land FeatureCollection (a single MultiPolygon)."""
    return json.loads(_LAND_PATH.read_text())
