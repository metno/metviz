"""Helpers that decide which variables/coordinates can be plotted and on which
axes, working uniformly across gridded and DSG (Discrete Sampling Geometry)
NetCDF layouts.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

# Names that identify coordinate / axis variables — not useful as plotted data.
# Used by :func:`is_plottable` to exclude these from the *variable* selector.
# Checked against the lower-cased variable name.
_COORD_LIKE_NAMES: frozenset[str] = frozenset({
    # Spatial coordinates
    "latitude", "longitude", "lat", "lon",
    "depth", "z", "altitude", "alt", "height",
    "pressure", "pres", "lev", "level",
    # Temporal
    "time",
    # DSG structural dimensions
    "station", "profile", "trajectory", "obs",
    "row_size", "rowsize",
    # Per-station / per-profile metadata scalars (not per-observation values)
    "bottomdepth", "bottom_depth",
})

# Variable-name suffixes that indicate identifiers, metadata, or QC variables —
# excluded from the *variable* selector. Extend this tuple as needed.
_EXCLUDE_SUFFIXES: tuple[str, ...] = (
    # QC / flags
    "_qc", "_flag", "flag", "qc", "woce", "_err", "_error", "_status",
    # Identifier / index columns
    "idall", "_id", "id",
)

# Names to exclude from the *dimension* selector even when they are legitimate
# coordinate variables. Rationale: latitude/longitude are spatial coordinates,
# but plotting data vs. lat/lon is rarely intended — users almost always want
# time, depth, or pressure instead.
AXIS_BLACKLIST: frozenset[str] = frozenset({
    "latitude", "longitude", "lat", "lon",
    "altitude", "alt", "height",
    "station", "profile", "trajectory",
    "row_size", "rowsize",
})

# dtype kinds that count as numeric: float, signed int, unsigned int.
_NUMERIC_KINDS = "fiu"


def is_time_like(ds: xr.Dataset, name: str) -> bool:
    """Return ``True`` if *name* refers to a datetime-like axis in *ds*."""
    try:
        idx = ds.indexes.get(name)
        if idx is not None:
            return idx.dtype.kind in "Mm" or isinstance(idx, xr.CFTimeIndex)
        return np.issubdtype(ds[name].dtype, np.datetime64)
    except Exception:
        return False


def is_plottable(name: str, var: xr.DataArray) -> bool:
    """Return ``True`` if *var* looks like a numeric data variable worth plotting.

    Rules:
    - Must have at least one dimension.
    - Must be a numeric dtype (float / integer — not string / object / bool).
    - Name must not be a well-known coordinate / axis identifier.
    - Name must not end with a recognised QC / flag suffix.
    """
    if var.ndim < 1:
        return False
    if var.dtype.kind not in _NUMERIC_KINDS:
        return False
    name_l = name.lower()
    if name_l in _COORD_LIKE_NAMES:
        return False
    return not any(name_l.endswith(s) for s in _EXCLUDE_SUFFIXES)


def safe_check_var(ds: xr.Dataset, var: str) -> bool:
    """Return ``True`` if *var* can be materialised from *ds* without error.

    Guards against remote/lazy variables that raise on access (e.g. broken
    OPeNDAP slices) so they never reach the plotting code.
    """
    try:
        _ = ds[var].values  # force materialisation to surface lazy/remote errors
        return True
    except Exception as exc:
        print(f"safe_check: cannot load {var!r}: {exc}")
        return False


def get_plottable_vars(ds: xr.Dataset) -> list[str]:
    """Return data-variable names in *ds* suitable for x-y plotting.

    Uses ``ds.data_vars`` (excluding proper coordinate variables), then applies
    :func:`is_plottable` and a live-access check. This works for DSG datasets
    where the observation dimension is not registered as a named coordinate.
    """
    return [
        name for name in ds.data_vars
        if is_plottable(name, ds[name]) and safe_check_var(ds, name)
    ]


def get_axis_candidates(ds: xr.Dataset, var_name: str) -> list[str]:
    """Return variable/coordinate names usable as the x or y axis for *var_name*.

    Only coordinate-like names are returned — never other data variables such
    as temperature or salinity, which belong in the variable selector instead.

    Priority order:
    1. Named dimension indexes already registered on the variable (proper dim
       coords — e.g. ``time``, ``depth`` when set as xarray indexes).
    2. 1-D *coordinate* variables sharing one of the variable's dimensions with
       a datetime or numeric dtype (auxiliary coords like ``latitude(time)``).
    3. 1-D *data* variables sharing a dimension whose names are in
       ``_COORD_LIKE_NAMES`` — handles DSG datasets where ``z`` / ``pressure``
       land in ``data_vars`` because the file declares no ``coordinates`` attr.

    Falls back to the raw dimension name(s) so the selector is never empty.
    """
    var = ds[var_name]
    candidates: list[str] = []
    seen: set[str] = set()

    def _consider(name: str, source: xr.DataArray) -> None:
        if name in seen or name == var_name or name.lower() in AXIS_BLACKLIST:
            return
        if source.ndim != 1:
            return
        if source.dtype.kind in _NUMERIC_KINDS or np.issubdtype(
            source.dtype, np.datetime64
        ):
            candidates.append(name)
            seen.add(name)

    # 1. Named indexes (proper dimension coordinates)
    for idx_name in var.indexes:
        if idx_name in seen or idx_name.lower() in AXIS_BLACKLIST:
            continue
        candidates.append(idx_name)
        seen.add(idx_name)

    for dim in var.dims:
        # 2. Auxiliary coordinates sharing this dimension
        for name in ds.coords:
            coord = ds[name]
            if coord.dims[:1] == (dim,):
                _consider(name, coord)

        # 3. Data variables with coordinate-like names sharing this dimension
        for name in ds.data_vars:
            if name.lower() not in _COORD_LIKE_NAMES:
                continue
            dv = ds[name]
            if dv.dims[:1] == (dim,):
                _consider(name, dv)

    # 4. Fall back to the raw dimension name so the selector is never empty
    for dim in var.dims:
        if dim not in seen:
            candidates.append(dim)
            seen.add(dim)

    return candidates


def sort_axis_candidates(ds: xr.Dataset, names: list[str]) -> list[str]:
    """Sort axis candidates so time-like names come first (sensible default)."""
    return sorted(names, key=lambda n: (0 if is_time_like(ds, n) else 1, n))
