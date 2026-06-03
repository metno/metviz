"""Pydantic models and helpers for the METAPI service.

CF Discrete-Sampling-Geometry featureTypes:
    point              individual points
    timeSeries         a single fixed point varying in time
    trajectory         a single point moving in time
    profile            a vertical profile at a fixed location and time
    timeSeriesProfile  a time series of vertical profiles
    trajectoryProfile  a moving vertical profile (e.g. aircraft or glider)
"""

from enum import StrEnum

import xarray as xr
from pydantic import AnyHttpUrl, BaseModel, field_validator


class FeatureTypeEnum(StrEnum):
    POINT = "point"
    TIMESERIES = "timeSeries"
    TRAJECTORY = "trajectory"
    PROFILE = "profile"
    TIMESERIESPROFILE = "timeSeriesProfile"
    TRAJECTORYPROFILE = "trajectoryProfile"


class FeatureType(BaseModel):
    """Validates that a value is one of the recognised CF featureTypes."""

    value: FeatureTypeEnum


class URLStr(BaseModel):
    """Validates that a string is a well-formed HTTP(S) URL."""

    url: AnyHttpUrl


class OpendapURL(URLStr):
    """A URL that must resolve to an OPeNDAP dataset carrying a featureType."""

    @field_validator("url")
    @classmethod
    def validate_opendap_url(cls, v: AnyHttpUrl) -> AnyHttpUrl:
        try:
            with xr.open_dataset(str(v)) as ds:
                if "featureType" not in ds.attrs:
                    raise ValueError(
                        "URL does not point to a valid OPeNDAP dataset with a featureType attribute"
                    )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"URL cannot be opened as an OPeNDAP dataset: {exc}") from exc
        return v


def guess_feature_type_from_data(data) -> str | None:
    """Return the ``featureType`` attribute of the dataset at *data*, or ``None``.

    Times are not decoded — only the global attributes are needed. Raises
    ``ValueError`` if the URL cannot be opened as a dataset.
    """
    url = str(data)
    try:
        with xr.open_dataset(url, decode_times=False) as ds:
            return ds.attrs.get("featureType", None)
    except Exception as exc:
        raise ValueError(f"URL cannot be opened as an OPeNDAP dataset: {exc}") from exc
