"""Map a detected CF ``featureType`` to the visualization app that handles it.

Shared by the Catalog and OGC_client apps so dataset selection routes to the
same place regardless of where the URL came from.
"""

from __future__ import annotations

# featureType (lower-cased) -> Panel app route.
FEATURE_TYPE_APP = {
    "timeseries": "TSP",
    "profile": "TSP",
    "timeseriesprofile": "TSP",
    "trajectory": "TRJ",
}


def target_app_for(feature_type: str | None) -> str:
    """Return the app route (``TSP`` / ``TRJ``) for *feature_type*.

    Unknown / undetected types fall back to ``TSP``, which covers the common
    1-D feature types.
    """
    if feature_type:
        return FEATURE_TYPE_APP.get(feature_type.lower(), "TSP")
    return "TSP"
