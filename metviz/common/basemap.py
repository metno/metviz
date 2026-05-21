"""Lightweight, projection-agnostic land basemap.

A Natural Earth 110m land polygon set (EPSG:4326) bundled with the package.
Rendered as a Leaflet GeoJSON vector layer it reprojects into any map CRS —
including custom polar projections that have no public tile basemap.
"""

from __future__ import annotations

import json
from pathlib import Path

_LAND_PATH = Path(__file__).parent / "ne_110m_land.geojson"


def _max_lat(coords) -> float:
    """Largest latitude in a GeoJSON coordinate structure (any nesting depth)."""
    if isinstance(coords[0], (int, float)):
        return coords[1]
    return max(_max_lat(c) for c in coords)


def land_geojson(min_lat: float | None = None) -> dict:
    """Return the land FeatureCollection, optionally only northern features.

    *min_lat* drops features whose maximum latitude is below it — use it for
    polar maps (e.g. UPS North), which are undefined in the southern hemisphere.
    """
    data = json.loads(_LAND_PATH.read_text())
    if min_lat is None:
        return data
    features = [f for f in data["features"] if _max_lat(f["geometry"]["coordinates"]) >= min_lat]
    return {**data, "features": features}
