"""URL validation and CF ``featureType`` detection helpers."""

from __future__ import annotations

import xarray as xr
from pydantic import AnyHttpUrl, BaseModel, ValidationError


class ModelURL(BaseModel):
    """Pydantic model used to validate that a string is a valid HTTP(S) URL.

    Example:
        >>> ModelURL(url="https://thredds.met.no/...")  # ok
        >>> ModelURL(url="ftp://invalid")               # raises ValidationError
    """

    url: AnyHttpUrl


def validate_url(url: str) -> bool:
    """Return ``True`` if *url* is a syntactically valid HTTP(S) URL."""
    try:
        ModelURL(url=str(url))
        return True
    except (ValidationError, TypeError):
        return False


def validate_opendap(url: str) -> bool:
    """Return ``True`` if *url* can actually be opened as a dataset by xarray.

    Times are intentionally left undecoded here: this is a cheap reachability
    check, and decoding can fail on otherwise-valid datasets with non-standard
    calendars.
    """
    try:
        with xr.open_dataset(str(url), decode_times=False):
            return True
    except (TypeError, OSError):
        return False


def detect_feature_type(ds: xr.Dataset) -> str | None:
    """Return the dataset's CF ``featureType`` (lower-cased) or ``None``.

    Resolution order:
    1. The global ``featureType`` attribute (CF-convention DSG datasets).
    2. The ``cdm_data_type`` attribute on the first coordinate's variable
       (some THREDDS/ERDDAP datasets expose it there instead).
    """
    feature_type = ds.attrs.get("featureType")
    if feature_type:
        return str(feature_type).lower()

    if ds.coords:
        first_coord = next(iter(ds.coords))
        cdm = ds[first_coord].attrs.get("cdm_data_type")
        if cdm:
            return str(cdm).lower()
    return None
