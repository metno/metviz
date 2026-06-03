import pytest
from common.urls import detect_feature_type, validate_opendap, validate_url


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://thredds.met.no/thredds/dodsC/x.nc", True),
        ("http://example.org/data", True),
        ("ftp://example.org/data", False),
        ("not a url", False),
        (None, False),
    ],
)
def test_validate_url(url, expected):
    assert validate_url(url) is expected


def test_detect_feature_type_from_global_attr(timeseries_ds):
    timeseries_ds.attrs["featureType"] = "timeSeries"
    assert detect_feature_type(timeseries_ds) == "timeseries"


def test_detect_feature_type_from_cdm_data_type(timeseries_ds):
    # No global attr; first coordinate (time) carries cdm_data_type instead.
    timeseries_ds["time"].attrs["cdm_data_type"] = "Profile"
    assert detect_feature_type(timeseries_ds) == "profile"


def test_detect_feature_type_none(timeseries_ds):
    assert detect_feature_type(timeseries_ds) is None


def test_validate_opendap_rejects_garbage():
    # Offline: an unopenable path returns False rather than raising.
    assert validate_opendap("/definitely/not/a/dataset.nc") is False


@pytest.mark.network
def test_validate_opendap_live():
    url = "https://thredds.met.no/thredds/dodsC/arcticdata/obsSynop/01008"
    assert validate_opendap(url) is True
