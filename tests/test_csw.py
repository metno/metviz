import pytest
from common.csw import (
    CswRecord,
    extract_opendap_url,
    feature_type_from_record,
    parse_bbox,
    resolve_feature_type,
)
from common.routing import target_app_for


@pytest.mark.parametrize(
    "text, expected",
    [
        ("[-10.5, 60.1, 5.2, 70.3]", [-10.5, 60.1, 5.2, 70.3]),
        ("-10.5, 60.1, 5.2, 70.3", [-10.5, 60.1, 5.2, 70.3]),
        ("", None),
        (None, None),
        ("[1, 2, 3]", None),       # wrong length
        ("garbage", None),
    ],
)
def test_parse_bbox(text, expected):
    assert parse_bbox(text) == expected


def test_extract_opendap_url_by_scheme():
    refs = [
        {"scheme": "OGC:WMS", "url": "https://x/wms"},
        {"scheme": "OPeNDAP:OPeNDAP", "url": "https://x/dodsC/d.nc"},
    ]
    assert extract_opendap_url(refs) == "https://x/dodsC/d.nc"


def test_extract_opendap_url_by_dodsc_path():
    refs = [{"scheme": "WWW:LINK", "url": "https://thredds/dodsC/data.nc"}]
    assert extract_opendap_url(refs) == "https://thredds/dodsC/data.nc"


def test_extract_opendap_url_none():
    assert extract_opendap_url([{"scheme": "WWW:LINK", "url": "https://x/page.html"}]) is None
    assert extract_opendap_url([]) is None


@pytest.mark.parametrize(
    "subjects, expected",
    [
        (["timeSeries"], "timeseries"),
        (["time series"], "timeseries"),
        (["timeSeriesProfile"], "timeseriesprofile"),
        (["oceanography", "trajectory"], "trajectory"),
        (["oceanography"], None),
        ([], None),
    ],
)
def test_feature_type_from_record(subjects, expected):
    assert feature_type_from_record(subjects) == expected


def test_resolve_feature_type_from_metadata():
    record = CswRecord(identifier="x", title="t", subjects=["profile"])
    assert resolve_feature_type(record, probe=False) == "profile"


def test_resolve_feature_type_no_metadata_no_probe():
    record = CswRecord(identifier="x", title="t", subjects=["misc"])
    assert resolve_feature_type(record, probe=False) is None


def test_cswrecord_opendap_url_property():
    record = CswRecord(
        identifier="x",
        title="t",
        references=[{"scheme": "OPeNDAP:OPeNDAP", "url": "https://x/dodsC/d.nc"}],
    )
    assert record.opendap_url == "https://x/dodsC/d.nc"


@pytest.mark.parametrize(
    "feature_type, app",
    [
        ("trajectory", "TRJ"),
        ("timeseries", "TSP"),
        ("timeSeries", "TSP"),
        ("profile", "TSP"),
        ("timeseriesprofile", "TSP"),
        (None, "TSP"),
        ("weird", "TSP"),
    ],
)
def test_target_app_for(feature_type, app):
    assert target_app_for(feature_type) == app
