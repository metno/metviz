"""Dependency-light dataset preparation shared by the plot path and the export
(download) worker.

The TSP Panel app and the ``ncapp`` Celery export worker must agree on *how a
dataset is opened and cleaned* so that a downloaded file reproduces exactly what
the user saw plotted. This module is the single source of truth for that:

  * opening over OPeNDAP with CF time-decoding (and the no-decode fallback),
  * the ERDDAP "no coordinates" fix-up,
  * the NetCDF fill-value masking applied before plotting/export,
  * the UI-label → pandas-offset table used for resampling.

It deliberately imports only ``numpy``/``xarray`` — no ``panel``/``holoviews`` —
so the Celery worker can reuse it without pulling in the GUI stack. The cached,
Panel-aware wrapper (:func:`common.data.load_data`) and the plotting code build
on top of it.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

# CF/NetCDF "no data" fill value used by many of the OPeNDAP datasets we serve.
# Masked to NaN before both plotting and export so neither shows the sentinel.
FILL_VALUE = 9.96921e36

# Map the resampling-frequency labels shown in the UI to pandas offset aliases.
pandas_frequency_offsets: dict[str, str] = {
    "Hourly": "h",
    "Calendar day": "D",
    "Weekly": "W",
    "Month end": "ME",
    "Quarter end": "QE",
    "Yearly": "YE",
}


def datetime_coords(ds: xr.Dataset) -> list[str]:
    """Return the names of datetime64 coordinates in *ds*."""
    return [
        name for name in ds.coords
        if np.issubdtype(ds.coords[name].dtype, np.datetime64)
    ]


def is_monotonic(ds: xr.Dataset) -> bool | None:
    """Return whether the dataset's time coordinate is monotonic.

    Returns ``None`` when the dataset has no datetime coordinate (the caller
    treats that as "resampling not applicable").
    """
    time_coords = datetime_coords(ds)
    if not time_coords:
        return None
    index = ds.indexes.get(time_coords[0])
    if index is not None:
        return bool(index.is_monotonic_increasing or index.is_monotonic_decreasing)
    values = ds.coords[time_coords[0]].values
    diffs = np.diff(values)
    return bool((diffs >= 0).all() or (diffs <= 0).all())


def fix_erddap_dataset(url: str) -> xr.Dataset:
    """Reopen an ERDDAP dataset that exposes no coordinates.

    Some ERDDAP OPeNDAP endpoints prefix every variable with the sequence/table
    name (e.g. ``s.time``) and register nothing as a coordinate. We probe the
    dataset, request the variables explicitly, then promote ``time`` to a
    proper indexed coordinate and strip the prefix from all variable names.

    Keeping this here (rather than in the plot path) means the export worker
    sees the same de-prefixed variable names the UI offered the user, so the
    ``variables`` list in an export spec selects correctly.
    """
    with xr.open_dataset(url) as probe:
        prefix = next(iter(probe.dims))
        renamed_vars = {
            name: name.replace(prefix + ".", "")
            for name in probe.variables
        }
        explicit_vars = (
            ",".join(probe.variables)
            .replace(f"{prefix}.", "")
            .replace("time,", "")
        )
        new_url = f"{url}?time,{explicit_vars}"

    ds = xr.open_dataset(new_url)
    ds = ds.set_coords(f"{prefix}.time")
    ds = ds.swap_dims(s="time")
    ds = ds.set_xindex(f"{prefix}.time")
    return ds.rename_vars(renamed_vars)


def open_decoded(url: str) -> tuple[xr.Dataset | None, bool, Exception | None]:
    """Open *url* the way the plot path does: ``(ds, decoded_time, error)``.

    - Tries CF time decoding first, falling back to ``decode_times=False`` when
      the calendar/units cannot be decoded.
    - Applies the ERDDAP fix-up when the opened dataset has no coordinates.
    - ``error`` carries the original exception when a fallback was needed (or
      when opening failed entirely, in which case ``ds`` is ``None``).
    """
    ds: xr.Dataset | None = None
    decoded_time = False
    error: Exception | None = None

    try:
        ds = xr.open_dataset(str(url).strip())
        decoded_time = True
    except ValueError as exc:
        print(exc)
        ds = xr.open_dataset(str(url).strip(), decode_times=False)
        error = exc
    except OSError as exc:
        error = exc

    if ds is None:
        return None, decoded_time, error

    if not ds.coords:
        ds.close()
        ds = fix_erddap_dataset(str(url))

    return ds, decoded_time, error


def mask_fill(obj, *, fill_value: float = FILL_VALUE):
    """Return *obj* with :data:`FILL_VALUE` entries replaced by NaN.

    Works on a ``DataArray`` or ``Dataset`` (xarray's ``.where`` broadcasts
    over a whole dataset's data variables). Mirrors the masking the plot applies
    so exports contain the same values the user saw.
    """
    return obj.where(obj != fill_value)
