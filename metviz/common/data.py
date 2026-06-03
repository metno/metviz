"""Dataset loading and time-axis inspection (Panel-aware wrapper).

The pure open/decode/ERDDAP-fix-up/masking logic lives in
:mod:`common.dataprep` so the export worker can reuse it without the GUI stack.
This module adds the Panel session cache and the feature-type/monotonic summary
the apps consume.
"""

from __future__ import annotations

import panel as pn
import xarray as xr

# Re-exported so existing callers (and tests) can keep importing them from here.
from .dataprep import datetime_coords as _datetime_coords  # noqa: F401
from .dataprep import is_monotonic, open_decoded  # noqa: F401
from .urls import detect_feature_type


@pn.cache(per_session=True, max_items=10, ttl=600)
def load_data(url: str) -> tuple[xr.Dataset | None, bool, Exception | None, bool | None, str | None]:
    """Open *url* with xarray and return ``(ds, decoded_time, error, monotonic, featureType)``.

    Delegates the opening (CF decode + fallback + ERDDAP fix-up) to
    :func:`common.dataprep.open_decoded`, then derives the feature type and the
    monotonic flag for the UI.

    - ``error`` carries the original exception when a fallback was needed (or
      when opening failed entirely, in which case ``ds`` is ``None``).
    - ``monotonic`` is only meaningful for the ``timeseries`` featureType;
      it is ``None`` otherwise.
    """
    ds, decoded_time, error = open_decoded(url)
    if ds is None:
        return None, decoded_time, error, None, None

    feature_type = detect_feature_type(ds)
    monotonic = is_monotonic(ds) if feature_type == "timeseries" else None
    return ds, decoded_time, error, monotonic, feature_type
