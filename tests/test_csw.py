from functools import partial
from types import SimpleNamespace

import pytest
from common.csw import (
    CswRecord,
    _bbox_tuple,
    _iso_keywords,
    _iso_references,
    build_filter,
    collect_page,
    collect_page_parallel,
    count_hits,
    extract_opendap_url,
    extract_wms_url,
    feature_type_from_record,
    get_page,
    keep_with_feature_type,
    keep_with_wms,
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
        csw, [], start_cursor=1, page_size=10, fetch_size=10,
        keep=partial(keep_with_feature_type, probe=False),
    )
    assert [r.identifier for r in records] == ["a"]
    assert records[0].feature_type == "timeseries"
    assert end is True          # chunk shorter than fetch_size -> exhausted
    assert matches == 42        # CSW total, not the filtered count


class _BigCsw:
    """A huge catalogue whose records never match — to test the scan cap."""

    def __init__(self):
        self.records = {}
        self.results = {}

    def getrecords2(self, *, startposition, maxrecords, **kwargs):
        self.records = {
            f"r{startposition + i}": SimpleNamespace(
                identifier=f"r{startposition + i}", title="t", references=[], subjects=[]
            )
            for i in range(maxrecords)
        }
        self.results = {"matches": 100_000, "returned": maxrecords, "nextrecord": startposition + maxrecords}


def test_collect_page_scan_cap_terminates_without_exhausting():
    csw = _BigCsw()
    records, next_cursor, end, matches = collect_page(
        csw, [], start_cursor=1, page_size=10, fetch_size=10,
        keep=lambda r: False, max_scan=30,
    )
    assert records == []          # nothing matched
    assert next_cursor == 31      # scanned 3 chunks of 10 then stopped
    assert end is False           # not exhausted -> Next can continue
    assert matches == 100_000


class _HitsCsw:
    """Records the getrecords2 kwargs and reports a fixed match count."""

    def __init__(self, matches):
        self.results = {"matches": matches}
        self.last_call = None

    def getrecords2(self, **kwargs):
        self.last_call = kwargs


def test_count_hits_uses_hits_resulttype_and_returns_matches():
    csw = _HitsCsw(matches=1234)
    assert count_hits(csw, []) == 1234
    assert csw.last_call["resulttype"] == "hits"
    assert csw.last_call["maxrecords"] == 0


def test_count_hits_missing_matches_is_zero():
    csw = _HitsCsw(matches=None)
    assert count_hits(csw, []) == 0


class _PoolCsw:
    """Fake CSW returning position-sequential records up to *total*."""

    def __init__(self, total=100_000, per=10):
        self.total = total
        self.per = per
        self.records = {}
        self.results = {}

    def getrecords2(self, *, startposition, maxrecords, **kwargs):
        remaining = max(0, self.total - startposition + 1)
        n = min(self.per, maxrecords, remaining)
        self.records = {
            f"r{startposition + i}": SimpleNamespace(
                identifier=f"r{startposition + i}", title="t", references=[], subjects=[]
            )
            for i in range(n)
        }
        self.results = {"matches": self.total, "returned": n, "nextrecord": startposition + n}


def _pool(n=8, **kw):
    return [_PoolCsw(**kw) for _ in range(n)]


def test_collect_page_parallel_keeps_matches_in_order_and_exhausts():
    records, next_cursor, end, matches = collect_page_parallel(
        _pool(total=30), [], start_cursor=1, page_size=10, fetch_size=10,
        keep=lambda r: r.identifier in {"r5", "r17"}, max_scan=100,
    )
    assert [r.identifier for r in records] == ["r5", "r17"]  # ascending position order
    assert end is True            # result set exhausted at 30
    assert matches == 30


def test_collect_page_parallel_fills_page_with_exact_resume_cursor():
    records, next_cursor, end, matches = collect_page_parallel(
        _pool(total=1000), [], start_cursor=1, page_size=10, fetch_size=10,
        keep=lambda r: True, max_scan=1000,
    )
    assert [r.identifier for r in records] == [f"r{i}" for i in range(1, 11)]
    assert next_cursor == 11       # resume right after the 10th kept record
    assert end is False


def test_collect_page_parallel_scan_cap_terminates_without_exhausting():
    records, next_cursor, end, matches = collect_page_parallel(
        _pool(total=100_000), [], start_cursor=1, page_size=10, fetch_size=10,
        keep=lambda r: False, max_scan=30,
    )
    assert records == []
    assert next_cursor == 31       # scanned 3 chunks of 10 then stopped
    assert end is False
    assert matches == 100_000


def test_extract_wms_url_by_protocol_and_url():
    assert extract_wms_url(
        [{"scheme": "OGC:WMS", "url": "https://x/thredds/wms/a?SERVICE=WMS&REQUEST=GetCapabilities"}]
    ) == "https://x/thredds/wms/a?SERVICE=WMS&REQUEST=GetCapabilities"
    # matched by URL even when the protocol is generic
    assert extract_wms_url([{"scheme": "WWW:LINK", "url": "https://x/geoserver/wms?service=WMS"}])
    # OPeNDAP-only record has no WMS
    assert extract_wms_url([{"scheme": "OPeNDAP:OPeNDAP", "url": "https://x/dodsC/a.nc"}]) is None
    assert extract_wms_url([]) is None


def test_keep_with_wms_is_metadata_only():
    wms_rec = CswRecord("a", "A", references=[{"scheme": "OGC:WMS", "url": "https://x/wms?service=WMS"}])
    plain_rec = CswRecord("b", "B", references=[{"scheme": "download", "url": "https://x/a.nc"}])
    assert keep_with_wms(wms_rec) is True
    assert keep_with_wms(plain_rec) is False
    assert wms_rec.wms_url == "https://x/wms?service=WMS"


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


def test_build_filter_require_only():
    # A lone required AnyText term is one un-wrapped constraint.
    result = build_filter(require=["WMS"])
    assert len(result) == 1
    assert isinstance(result[0], fes.PropertyIsLike)


def test_build_filter_require_is_anded_with_text():
    # text OR-group AND the required "WMS" term -> a single And of two operands.
    result = build_filter(text="sentinel", require=["WMS"])
    assert len(result) == 1
    assert isinstance(result[0], fes.And)


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
