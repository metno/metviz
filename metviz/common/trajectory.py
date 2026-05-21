"""Helpers for trajectory datasets: extract the track, its bounds, and a couple
of summary stats. Kept free of any map/UI dependency so apps can reuse them.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

_LAT_NAMES = ("latitude", "lat", "Latitude", "LATITUDE")
_LON_NAMES = ("longitude", "lon", "Longitude", "LONGITUDE")


def _find_var(ds: xr.Dataset, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in ds.variables:
            return name
    return None


def latlon_names(ds: xr.Dataset) -> tuple[str | None, str | None]:
    """Return the (latitude, longitude) variable names present in *ds*, or None."""
    return _find_var(ds, _LAT_NAMES), _find_var(ds, _LON_NAMES)


def track_points(ds: xr.Dataset) -> list[list[float]]:
    """Return the trajectory as a list of ``[lat, lon]`` points (``[]`` if absent)."""
    lat_name, lon_name = latlon_names(ds)
    if lat_name is None or lon_name is None:
        return []
    lats = np.asarray(ds[lat_name].values).ravel()
    lons = np.asarray(ds[lon_name].values).ravel()
    return [
        [float(la), float(lo)]
        for la, lo in zip(lats, lons, strict=False)
        if np.isfinite(la) and np.isfinite(lo)
    ]


def track_bounds(points: list[list[float]]) -> list[list[float]] | None:
    """Return ``[[min_lat, min_lon], [max_lat, max_lon]]`` for fit-bounds, or None."""
    if not points:
        return None
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def geodesic_length_km(points: list[list[float]]) -> float:
    """Total along-track distance in km (WGS84 geodesic)."""
    if len(points) < 2:
        return 0.0
    from geographiclib.geodesic import Geodesic  # lazy: optional dependency

    geod = Geodesic.WGS84
    total_m = sum(
        geod.Inverse(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])["s12"]
        for i in range(1, len(points))
    )
    return total_m / 1000.0


def duration_hours(ds: xr.Dataset, time_dim: str = "time") -> float:
    """Total trajectory duration in hours (0 if fewer than two timestamps)."""
    if time_dim not in ds.variables:
        return 0.0
    times = np.asarray(ds[time_dim].values)
    if times.size < 2:
        return 0.0
    seconds = (np.datetime64(times[-1]) - np.datetime64(times[0])) / np.timedelta64(1, "s")
    return float(seconds) / 3600.0
