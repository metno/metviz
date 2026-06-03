"""Helpers that decide which variables/coordinates can be plotted and on which
axes, working uniformly across gridded and DSG (Discrete Sampling Geometry)
NetCDF layouts.
"""

from __future__ import annotations

import re

import numpy as np
import xarray as xr

# CF/NetCDF "no data" fill value; single source of truth in `common.dataprep`.
from .dataprep import FILL_VALUE as _FILL_VALUE

# Legacy coordinate-like names. Applied *only* as a fallback when a variable
# lacks CF metadata (no standard_name) — modern files are routed through
# `axis` / `cf_role` / cross-reference checks first. Lower-cased.
#
# `pressure` is intentionally absent: it is a vertical coord in profile files
# but an atmospheric observation in trajectory/timeseries files. CF `axis: Z`
# or being listed in another variable's `coordinates` is the correct signal.
_COORD_LIKE_NAMES: frozenset[str] = frozenset({
    "latitude", "longitude", "lat", "lon",
    "depth", "z", "altitude", "alt", "height",
    "pres", "lev", "level",
    "time",
    "station", "profile", "trajectory", "obs",
    "row_size", "rowsize",
    "bottomdepth", "bottom_depth",
})

# Underscore-anchored QC / error / flag suffix matcher. Anchoring on `_` keeps
# `humidity` (ends in 'id'), `gradient_grid`, etc. from being wrongly dropped
# by accidental substring matches.
_QC_SUFFIX_RE = re.compile(r"(_qc|_flag|_status|_err(?:or)?|_woce|woceflag)$")

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

    CF-first: the file's own metadata is the primary signal; the legacy
    coord-name list is only consulted when no ``standard_name`` is set.

    Rules:
    - 1-D-or-more, numeric (float / int / unsigned).
    - Not a coord axis (``axis`` attr) or DSG identifier (``cf_role`` attr).
    - Not a QC variable (``standard_name`` ending in ``status_flag`` /
      ``quality_flag``, or a name ending in a recognised QC suffix).
    - When the variable lacks a ``standard_name``, fall back to the legacy
      coord-like-name set — files without CF annotation need the safety net.
    """
    if var.ndim < 1:
        return False
    if var.dtype.kind not in _NUMERIC_KINDS:
        return False
    if var.attrs.get("axis"):
        return False
    if var.attrs.get("cf_role"):
        return False
    standard_name = var.attrs.get("standard_name", "")
    if standard_name.endswith(("status_flag", "quality_flag")):
        return False
    if _QC_SUFFIX_RE.search(name.lower()):
        return False
    if not standard_name and name.lower() in _COORD_LIKE_NAMES:
        return False
    return True


def safe_check_var(ds: xr.Dataset, var: str) -> bool:
    """Return ``True`` if *var* is structurally readable from *ds*.

    Peeks at shape and dtype — cheap metadata reads — rather than materialising
    the array, which would pull the entire variable over OPeNDAP just to
    confirm it loads.
    """
    try:
        _ = ds[var].shape
        _ = ds[var].dtype
        return True
    except Exception as exc:
        print(f"safe_check: cannot describe {var!r}: {exc}")
        return False


def is_empty(ds: xr.Dataset, name: str, *, fill_value: float = _FILL_VALUE) -> bool:
    """Return ``True`` if *name* contains no finite, non-fill values.

    Fetches the variable's data — caller is responsible for running this off
    the request thread when the dataset is remote.
    """
    try:
        da = ds[name]
        return int(da.where(da != fill_value).count()) == 0
    except Exception as exc:
        print(f"is_empty: cannot inspect {name!r}: {exc}")
        return False


def _referenced_coords(ds: xr.Dataset) -> set[str]:
    """Names another data variable points to via CF coordinate references.

    A variable that appears in any other variable's ``coordinates``,
    ``bounds``, ``ancillary_variables`` or ``cell_measures`` attribute is
    structural to that variable — not itself a plotting target.
    """
    refs: set[str] = set()
    for v in ds.data_vars.values():
        for key in ("coordinates", "bounds", "ancillary_variables", "cell_measures"):
            val = v.attrs.get(key, "")
            if val:
                refs.update(val.split())
    return refs


def get_plottable_vars(ds: xr.Dataset) -> list[str]:
    """Return data-variable names in *ds* suitable for x-y plotting.

    Combines :func:`is_plottable` (per-variable CF checks) with a dataset-wide
    cross-reference sweep that drops anything another variable already
    declares as one of its coordinates / bounds / ancillary fields.
    """
    referenced = _referenced_coords(ds)
    return [
        name for name in ds.data_vars
        if name not in referenced
        and is_plottable(name, ds[name])
        and safe_check_var(ds, name)
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
