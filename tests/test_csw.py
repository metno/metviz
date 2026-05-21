from types import SimpleNamespace

import pytest
from common.csw import (
    CswRecord,
    _bbox_tuple,
    _iso_keywords,
    _iso_references,
    build_filter,
    collect_page,
    extract_opendap_url,
    feature_type_from_record,
    get_page,
    parse_bbox,
    resolve_feature_type,
)
from common.routing import target_app_for
from owslib import fes


class _FakeCsw:
    """Minimal stand-in for owslib CatalogueServiceWeb for get_page tests."""

    def __init__(self):
        self.records = {}
        self.results = {}
        self.last_call = None

    def getrecords2(self, **kwargs):
        self.last_call = kwargs
        self.records = {
            "a": SimpleNamespace(identifier="a", title="A", references=[], subjects=["timeSeries"]),
            "b": SimpleNamespace(identifier="b", title="B", references=[], subjects=[]),
        }
        self.results = {"matches": 42, "returned": 2, "nextrecord": 3}


def test_get_page_passes_paging_params_and_converts_records():
    csw = _FakeCsw()
    records, results = get_page(csw, [], startposition=11, pagesize=10)
    assert csw.last_call["startposition"] == 11
    assert csw.last_call["maxrecords"] == 10
    assert [r.identifier for r in records] == ["a", "b"]
    assert all(isinstance(r, CswRecord) for r in records)
    assert results["matches"] == 42 and results["returned"] == 2


def test_collect_page_keeps_only_featuretype_records_and_terminates():
    # The fake returns 2 records (one with a featureType keyword, one without)
    # and a short chunk, so the scan ends after one fetch.
    csw = _FakeCsw()
    records, next_cursor, end, matches = collect_page(
        csw, [], start_cursor=1, page_size=10, fetch_size=10, probe=False
    )
    assert [r.identifier for r in records] == ["a"]
    assert records[0].feature_type == "timeseries"
    assert end is True          # chunk shorter than fetch_size -> exhausted
    assert matches == 42        # CSW total, not the filtered count


def test_build_filter_single_text_term_not_wrapped_in_or():
    # Regression: fes.Or/And require >= 2 operands; a lone term must not be
    # wrapped, or owslib raises "Binary operations ... require a minimum of two".
    result = build_filter(text="temperature")
    assert len(result) == 1
    assert isinstance(result[0], fes.PropertyIsLike)


def test_build_filter_multiple_text_terms_use_or():
    result = build_filter(text=["a", "b"])
    assert len(result) == 1
    assert isinstance(result[0], fes.Or)


def test_build_filter_combines_with_and():
    result = build_filter(text="temp", bbox=[-10.0, 60.0, 5.0, 70.0])
    assert len(result) == 1
    assert isinstance(result[0], fes.And)


def test_build_filter_empty_query():
    assert build_filter() == []


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


def test_iso_bbox_tuple_from_geographic_bounding_box():
    box = SimpleNamespace(minx="10", miny="60", maxx="12", maxy="62")
    assert _bbox_tuple(box) == (10.0, 60.0, 12.0, 62.0)
    assert _bbox_tuple(None) is None


def test_iso_keywords_flattens_and_includes_topics():
    ident = SimpleNamespace(
        keywords=[SimpleNamespace(keywords=[
            SimpleNamespace(name="timeSeries"),
            SimpleNamespace(name="ocean"),
        ])],
        topiccategory=["climatologyMeteorologyAtmosphere"],
    )
    assert _iso_keywords(ident) == ["timeSeries", "ocean", "climatologyMeteorologyAtmosphere"]


def test_iso_references_from_online_resources():
    md = SimpleNamespace(distribution=SimpleNamespace(online=[
        SimpleNamespace(protocol="OPeNDAP:OPeNDAP", url="https://x/dodsC/d.nc"),
    ]))
    refs = _iso_references(md)
    assert refs == [{"scheme": "OPeNDAP:OPeNDAP", "url": "https://x/dodsC/d.nc"}]
    # and the OPeNDAP extractor recognises it
    assert extract_opendap_url(refs) == "https://x/dodsC/d.nc"


def test_cswrecord_location_centre_of_bbox():
    record = CswRecord(identifier="x", title="t", bbox=(10.0, 60.0, 12.0, 62.0))
    assert record.location == (61.0, 11.0)  # (lat, lon)


def test_cswrecord_location_none_without_bbox():
    assert CswRecord(identifier="x", title="t").location is None


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
