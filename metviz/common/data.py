"""Dataset loading and time-axis inspection."""

from __future__ import annotations

import numpy as np
import panel as pn
import xarray as xr

from .urls import detect_feature_type


def _datetime_coords(ds: xr.Dataset) -> list[str]:
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
    time_coords = _datetime_coords(ds)
    if not time_coords:
        return None
    index = ds.indexes.get(time_coords[0])
    if index is not None:
        return bool(index.is_monotonic_increasing or index.is_monotonic_decreasing)
    values = ds.coords[time_coords[0]].values
    diffs = np.diff(values)
    return bool((diffs >= 0).all() or (diffs <= 0).all())


def _fix_erddap_dataset(url: str) -> xr.Dataset:
    """Reopen an ERDDAP dataset that exposes no coordinates.

    Some ERDDAP OPeNDAP endpoints prefix every variable with the sequence/table
    name (e.g. ``s.time``) and register nothing as a coordinate. We probe the
    dataset, request the variables explicitly, then promote ``time`` to a
    proper indexed coordinate and strip the prefix from all variable names.
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


@pn.cache(per_session=True, max_items=10, ttl=600)
def load_data(url: str) -> tuple[xr.Dataset | None, bool, Exception | None, bool | None, str | None]:
    """Open *url* with xarray and return ``(ds, decoded_time, error, monotonic, featureType)``.

    - Tries CF time decoding first, falling back to ``decode_times=False`` when
      the calendar/units cannot be decoded.
    - Applies an ERDDAP fix-up when the opened dataset has no coordinates.
    - ``error`` carries the original exception when a fallback was needed (or
      when opening failed entirely, in which case ``ds`` is ``None``).
    - ``monotonic`` is only meaningful for the ``timeseries`` featureType;
      it is ``None`` otherwise.
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
        return None, decoded_time, error, None, None

    if not ds.coords:
        ds.close()
        ds = _fix_erddap_dataset(str(url))

    feature_type = detect_feature_type(ds)
    monotonic = is_monotonic(ds) if feature_type == "timeseries" else None
    return ds, decoded_time, error, monotonic, feature_type
