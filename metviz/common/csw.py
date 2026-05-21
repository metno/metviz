"""OGC Catalogue Service for the Web (CSW) search helpers.

Wraps :mod:`owslib` to run space / time / free-text queries and return
structured records, plus helpers to pull the OPeNDAP link out of a record and
decide its CF ``featureType`` — preferring the metadata record, falling back to
probing the dataset.

Derived from the ioos exploring-csw notebook:
https://github.com/ioos/notebooks_demos/blob/master/notebooks/2016-12-19-exploring_csw.ipynb
"""

from __future__ import annotations

import ast
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from owslib import fes
from owslib.csw import CatalogueServiceWeb
from owslib.fes import SortBy, SortProperty
from owslib.iso import MD_Metadata

from .routing import target_app_for  # noqa: F401  (re-exported for callers)
from .urls import feature_type_from_url

try:  # geolinks is optional; we have URL/scheme fallbacks without it.
    from geolinks import sniff_link
except Exception:  # pragma: no cover
    sniff_link = None

# Recognized CF Discrete-Sampling-Geometry featureTypes (lower-cased, no spaces).
KNOWN_FEATURE_TYPES = frozenset({
    "point", "timeseries", "trajectory", "profile",
    "timeseriesprofile", "trajectoryprofile",
})

DEFAULT_CRS = "urn:ogc:def:crs:OGC:1.3:CRS84"

# Request ISO 19115/19139 (gmd) records by default — they carry a proper bounding
# box, keywords and online resources (OPeNDAP links), unlike sparse Dublin Core.
ISO_OUTPUT_SCHEMA = "http://www.isotc211.org/2005/gmd"

# Set METVIZ_CSW_DEBUG=1 to log each GetRecords request XML + result summary.
_CSW_DEBUG = bool(os.environ.get("METVIZ_CSW_DEBUG"))


@dataclass
class CswRecord:
    """A trimmed-down CSW metadata record."""

    identifier: str
    title: str
    references: list = field(default_factory=list)
    subjects: list = field(default_factory=list)
    feature_type: str | None = None
    bbox: tuple[float, float, float, float] | None = None  # (minx, miny, maxx, maxy)

    @property
    def opendap_url(self) -> str | None:
        return extract_opendap_url(self.references)

    @property
    def wms_url(self) -> str | None:
        return extract_wms_url(self.references)

    @property
    def location(self) -> tuple[float, float] | None:
        """Return ``(lat, lon)`` at the centre of the bbox, or ``None``.

        For a station/point record the bbox min and max coincide, so this is
        the station location.
        """
        if not self.bbox:
            return None
        minx, miny, maxx, maxy = self.bbox
        return ((miny + maxy) / 2.0, (minx + maxx) / 2.0)


def parse_bbox(text: str | None) -> list[float] | None:
    """Parse a bbox string like ``"[-10.5, 60.1, 5.2, 70.3]"`` into 4 floats.

    Accepts the Python-list / comma-separated forms produced by the map draw
    control. Returns ``None`` when the input is empty or malformed.
    """
    if not text:
        return None
    text = text.strip()
    try:
        values = ast.literal_eval(text) if text.startswith("[") else [float(x) for x in text.split(",")]
        coords = [float(v) for v in values]
    except (ValueError, SyntaxError):
        return None
    return coords if len(coords) == 4 else None


def fes_date_filter(start, stop, constraint: str = "overlaps"):
    """Build a pair of FES temporal-extent filters for a date range.

    *start* / *stop* are datetime-like (anything with ``strftime``). Minutes are
    truncated. ``constraint`` is ``"overlaps"`` (records overlapping the range)
    or ``"within"`` (records fully inside it).
    """
    start = start.strftime("%Y-%m-%d %H:00")
    stop = stop.strftime("%Y-%m-%d %H:00")
    if constraint == "overlaps":
        begin = fes.PropertyIsLessThanOrEqualTo(propertyname="apiso:TempExtent_begin", literal=stop)
        end = fes.PropertyIsGreaterThanOrEqualTo(propertyname="apiso:TempExtent_end", literal=start)
    elif constraint == "within":
        begin = fes.PropertyIsGreaterThanOrEqualTo(propertyname="apiso:TempExtent_begin", literal=start)
        end = fes.PropertyIsLessThanOrEqualTo(propertyname="apiso:TempExtent_end", literal=stop)
    else:
        raise ValueError(f"Unrecognized constraint {constraint!r}")
    return begin, end


def extract_opendap_url(references) -> str | None:
    """Return the OPeNDAP URL from a record's *references*, or ``None``.

    Looks for an OPeNDAP/DODS scheme, a ``/dodsC/`` THREDDS path, or — when
    :mod:`geolinks` is available — a sniffed ``OPeNDAP`` geolink.
    """
    for ref in references or []:
        url = ref.get("url", "") if isinstance(ref, dict) else getattr(ref, "url", "")
        scheme = (ref.get("scheme") if isinstance(ref, dict) else getattr(ref, "scheme", "")) or ""
        if "OPENDAP" in scheme.upper() or "DODS" in scheme.upper():
            return url
        if "/dodsC/" in url:
            return url
        if sniff_link is not None:
            try:
                if "OPENDAP" in (sniff_link(url) or "").upper():
                    return url
            except Exception:
                pass
    return None


def extract_wms_url(references) -> str | None:
    """Return a WMS service/GetCapabilities URL from a record's *references*.

    WMS is advertised in the metadata record (no dataset probing): an
    ``OGC:WMS`` online-resource protocol, or a URL with ``SERVICE=WMS`` /
    a ``/wms/`` THREDDS path.
    """
    for ref in references or []:
        url = ref.get("url", "") if isinstance(ref, dict) else getattr(ref, "url", "")
        scheme = (ref.get("scheme") if isinstance(ref, dict) else getattr(ref, "scheme", "")) or ""
        low = (url or "").lower()
        if "WMS" in scheme.upper():
            return url
        if "service=wms" in low or "/wms/" in low or "/wms?" in low or low.endswith("/wms"):
            return url
    return None


def feature_type_from_record(subjects) -> str | None:
    """Return a CF featureType found among a record's *subjects* (keywords).

    Matches a keyword that equals a known featureType (case-insensitive,
    spaces ignored), e.g. ``"timeSeries"`` or ``"time series"``.
    """
    for value in subjects or []:
        token = str(value).lower().replace(" ", "")
        if token in KNOWN_FEATURE_TYPES:
            return token
    return None


def resolve_feature_type(record: CswRecord, *, probe: bool = True) -> str | None:
    """Determine *record*'s featureType: metadata first, dataset probe fallback.

    Returns the lower-cased featureType, or ``None`` if it cannot be determined
    (record carries no featureType keyword and, when ``probe`` is enabled, the
    OPeNDAP dataset has no ``featureType`` attribute / cannot be opened).
    """
    ft = feature_type_from_record(record.subjects)
    if ft:
        return ft
    if probe and record.opendap_url:
        return feature_type_from_url(record.opendap_url)
    return None


def _bbox_tuple(bbox):
    """Coerce an object with minx/miny/maxx/maxy into a float tuple, or None."""
    if bbox is None:
        return None
    try:
        return (float(bbox.minx), float(bbox.miny), float(bbox.maxx), float(bbox.maxy))
    except (TypeError, ValueError, AttributeError):
        return None


def _iso_identification(md):
    idents = getattr(md, "identification", None) or []
    return idents[0] if idents else None


def _iso_keywords(ident):
    """Flatten an ISO identification's keywords (+ topic categories) to strings."""
    out: list[str] = []
    for mdkw in getattr(ident, "keywords", None) or []:
        for kw in getattr(mdkw, "keywords", None) or []:
            name = getattr(kw, "name", None) if not isinstance(kw, str) else kw
            if name:
                out.append(str(name))
    out.extend(str(t) for t in (getattr(ident, "topiccategory", None) or []) if t)
    return out


def _iso_references(md):
    """Map an ISO record's online resources to ``{scheme, url}`` dicts."""
    dist = getattr(md, "distribution", None)
    online = (getattr(dist, "online", None) or []) if dist else []
    return [
        {"scheme": getattr(res, "protocol", "") or "", "url": getattr(res, "url", "") or ""}
        for res in online
    ]


def _to_record(raw) -> CswRecord:
    """Normalise an owslib record (ISO ``MD_Metadata`` or Dublin Core) to a CswRecord."""
    if isinstance(raw, MD_Metadata):
        ident = _iso_identification(raw)
        return CswRecord(
            identifier=getattr(raw, "identifier", "") or "",
            title=(getattr(ident, "title", "") or "") if ident else "",
            references=_iso_references(raw),
            subjects=_iso_keywords(ident) if ident else [],
            bbox=_bbox_tuple(getattr(ident, "bbox", None)) if ident else None,
        )
    # Dublin Core (csw:Record) fallback.
    return CswRecord(
        identifier=getattr(raw, "identifier", "") or "",
        title=getattr(raw, "title", "") or "",
        references=list(getattr(raw, "references", []) or []),
        subjects=list(getattr(raw, "subjects", []) or []),
        bbox=_bbox_tuple(getattr(raw, "bbox", None)),
    )


def _get_records(csw, filter_list, pagesize: int, maxrecords: int) -> dict:
    """Page through ``getrecords2`` results up to *maxrecords*."""
    sortby = SortBy([SortProperty("dc:title", "ASC")])
    records: dict = {}
    startposition = 0
    while True:
        csw.getrecords2(
            constraints=filter_list,
            startposition=startposition,
            maxrecords=pagesize,
            sortby=sortby,
            outputschema=ISO_OUTPUT_SCHEMA,
            esn="full",
        )
        records.update(csw.records)
        nextrecord = csw.results.get("nextrecord", 0)
        if not nextrecord or len(records) >= maxrecords:
            break
        startposition = nextrecord
    return records


def build_filter(*, text=None, bbox=None, start=None, stop=None, crs: str = DEFAULT_CRS, require=None):
    """Build the FES filter list for a CSW query (no network).

    *text* is OR-combined free-text terms. *require* is a list of AnyText terms
    that must **all** match (ANDed) — used to narrow huge catalogues server-side
    (e.g. ``require=["WMS"]`` to find WMS-backed records without scanning).

    Returns a list suitable for ``getrecords2(constraints=...)``. ``fes.And`` /
    ``fes.Or`` require **at least two** operands, so a single free-text term is
    passed through un-wrapped and a lone constraint is not wrapped in an ``And``.
    An empty query returns ``[]`` (match everything).
    """
    kw = dict(wildCard="*", escapeChar="\\", singleChar="?", propertyname="apiso:AnyText")
    constraints = []

    if text:
        terms = [text] if isinstance(text, str) else list(text)
        likes = [fes.PropertyIsLike(literal=f"*{t}*", **kw) for t in terms]
        constraints.append(fes.Or(likes) if len(likes) > 1 else likes[0])

    if start is not None and stop is not None:
        begin, end = fes_date_filter(start, stop)
        constraints += [begin, end]

    if bbox:
        constraints.append(fes.BBox(bbox, crs=crs))

    for term in (require or []):
        constraints.append(fes.PropertyIsLike(literal=f"*{term}*", **kw))

    if len(constraints) >= 2:
        return [fes.And(constraints)]
    return constraints


# How many CSW connections to fetch chunks in parallel during a scan. The
# server caps each request at ~10 records, so the dominant cost is round-trip
# latency; fanning out across connections cuts a sparse scan several-fold.
SCAN_WORKERS = 8


def connect(endpoint: str, timeout: int = 60, skip_caps: bool = False) -> CatalogueServiceWeb:
    """Open a CSW connection.

    Reuse the returned object across page requests so capabilities are not
    re-fetched on every page turn. Pass ``skip_caps=True`` to skip the
    GetCapabilities round-trip — useful for cheap, throwaway connections in a
    parallel scan pool (``getrecords2`` does not need capabilities).
    """
    return CatalogueServiceWeb(endpoint, timeout=timeout, skip_caps=skip_caps)


def connect_pool(endpoint: str, size: int = SCAN_WORKERS, timeout: int = 60) -> list:
    """Return *size* lightweight (``skip_caps``) CSW connections for parallel scans.

    owslib's ``CatalogueServiceWeb`` is not thread-safe (each call mutates the
    instance), so a parallel scan needs one connection per worker thread.
    ``skip_caps`` makes each connection essentially free to create.
    """
    return [connect(endpoint, timeout=timeout, skip_caps=True) for _ in range(size)]


def get_page(
    csw,
    filter_list,
    *,
    startposition: int = 1,
    pagesize: int = 10,
    outputschema: str = ISO_OUTPUT_SCHEMA,
    esn: str = "full",
):
    """Fetch one page of CSW records (ISO ``gmd`` records by default).

    Returns ``(records, results)`` where *records* is a list of
    :class:`CswRecord` and *results* is the CSW result summary dict
    (``matches``, ``returned``, ``nextrecord``). Pair with
    :func:`resolve_feature_type` to label/filter just this page — far cheaper
    than probing every match up front.
    """
    sortby = SortBy([SortProperty("dc:title", "ASC")])
    csw.getrecords2(
        constraints=filter_list,
        startposition=startposition,
        maxrecords=pagesize,
        sortby=sortby,
        outputschema=outputschema,
        esn=esn,
    )
    if _CSW_DEBUG:
        _log_csw_request(csw)
    records = [_to_record(r) for r in csw.records.values()]
    return records, dict(csw.results)


def _log_csw_request(csw) -> None:
    """Print the CSW GetRecords request XML + result summary (debug aid)."""
    req = getattr(csw, "request", None)
    if isinstance(req, bytes):
        req = req.decode("utf-8", "replace")
    print("=== CSW getrecords2 request ===")
    print(req)
    print("=== CSW results:", {k: csw.results.get(k) for k in ("matches", "returned", "nextrecord")})


def keep_with_feature_type(record: CswRecord, *, probe: bool = True) -> bool:
    """Keep a record if it resolves to a featureType (sets ``feature_type``)."""
    ft = resolve_feature_type(record, probe=probe)
    if ft:
        record.feature_type = ft
        return True
    return False


def keep_with_wms(record: CswRecord) -> bool:
    """Keep a record if it advertises a WMS source (metadata only, no probe)."""
    return record.wms_url is not None


def count_hits(csw, filter_list) -> int:
    """Return how many records match *filter_list* — cheaply.

    Uses ``resultType="hits"`` so the server returns only the count, not the
    records. Call this before scanning to decide whether a query is too broad
    (and to avoid an expensive OPeNDAP probe-scan over a huge result set).
    """
    csw.getrecords2(constraints=filter_list, resulttype="hits", maxrecords=0)
    return int(csw.results.get("matches", 0) or 0)


def collect_page(
    csw,
    filter_list,
    *,
    start_cursor: int = 1,
    page_size: int = 10,
    fetch_size: int = 10,
    keep=None,
    max_scan: int = 500,
):
    """Scan CSW from *start_cursor*, keeping records for which ``keep(record)``
    is true, until *page_size* are collected or the result set is exhausted.

    This "fetch-and-refill" loop lets the UI show full pages of usable datasets
    without inspecting the entire match set up front: it pulls *fetch_size*
    records at a time and applies *keep* only to what it consumes. *keep*
    defaults to :func:`keep_with_feature_type`; pass :func:`keep_with_wms` (or
    any predicate) to filter differently. *max_scan* bounds how many records a
    single page will scan before giving up (so a huge catalogue with few/no
    matches doesn't scan indefinitely) — the next page resumes where it stopped.

    Returns ``(records, next_cursor, end, matches)``:

    - ``records``: up to *page_size* kept :class:`CswRecord`,
    - ``next_cursor``: CSW ``startposition`` to resume from for the next page,
    - ``end``: ``True`` only when the CSW result set is fully exhausted (not when
      merely scan-capped — Next can still continue),
    - ``matches``: the CSW total match count (NOT the filtered count, which is
      unknown until ``end`` is reached).
    """
    if keep is None:
        keep = keep_with_feature_type
    matched: list[CswRecord] = []
    cursor = start_cursor
    matches = 0
    end = False
    scanned = 0

    while len(matched) < page_size and not end:
        records, results = get_page(csw, filter_list, startposition=cursor, pagesize=fetch_size)
        matches = int(results.get("matches", 0) or 0)
        returned = len(records)
        if returned == 0:
            end = True
            break

        scanned += returned
        filled = False
        for offset_in_chunk, record in enumerate(records):
            if keep(record):
                matched.append(record)
                if len(matched) >= page_size:
                    # Resume the next page right after this record.
                    cursor += offset_in_chunk + 1
                    filled = True
                    break

        if not filled:
            cursor += returned
            if returned < fetch_size or cursor > matches:
                end = True
            elif scanned >= max_scan:
                # Stop scanning this page; the result set isn't exhausted, so the
                # next page can continue from `cursor`.
                break

    return matched, cursor, end, matches


def collect_page_parallel(
    connections,
    filter_list,
    *,
    start_cursor: int = 1,
    page_size: int = 10,
    fetch_size: int = 10,
    keep=None,
    max_scan: int = 500,
):
    """Parallel variant of :func:`collect_page` using a pool of *connections*.

    Same contract and return value as :func:`collect_page`, but each scan
    "wave" fetches ``len(connections)`` chunks concurrently (one per
    connection) instead of one at a time. Chunks are processed in ascending
    position order so the resume *cursor* stays exact: when a page fills
    mid-chunk, scanning of later (already-fetched) chunks is discarded and the
    next page re-fetches from the precise resume position.
    """
    if keep is None:
        keep = keep_with_feature_type
    workers = max(1, len(connections))
    matched: list[CswRecord] = []
    cursor = start_cursor
    matches = 0
    end = False
    scanned = 0

    def _fetch(conn_pos):
        conn, pos = conn_pos
        records, results = get_page(conn, filter_list, startposition=pos, pagesize=fetch_size)
        return pos, records, results

    while len(matched) < page_size and not end and scanned < max_scan:
        positions = [cursor + i * fetch_size for i in range(workers)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            wave = sorted(pool.map(_fetch, zip(connections, positions, strict=False)), key=lambda t: t[0])

        filled = False
        capped = False
        for pos, records, results in wave:
            matches = int(results.get("matches", 0) or 0) or matches
            returned = len(records)
            if returned == 0:
                end = True
                break
            scanned += returned
            for offset_in_chunk, record in enumerate(records):
                if keep(record):
                    matched.append(record)
                    if len(matched) >= page_size:
                        cursor = pos + offset_in_chunk + 1
                        filled = True
                        break
            if filled:
                break
            cursor = pos + returned
            if returned < fetch_size or cursor > matches:
                end = True
                break
            if scanned >= max_scan:
                capped = True
                break
        if filled or end or capped:
            break

    return matched, cursor, end, matches


def search(
    endpoint: str,
    *,
    text=None,
    bbox: list[float] | None = None,
    start=None,
    stop=None,
    maxrecords: int = 50,
    pagesize: int = 10,
    timeout: int = 60,
    crs: str = DEFAULT_CRS,
) -> list[CswRecord]:
    """Run a CSW query and return structured records.

    *text* is a string or list of free-text terms (apiso:AnyText, OR-combined).
    *bbox* is ``[minx, miny, maxx, maxy]`` in *crs*. *start* / *stop* are
    datetime-like; both must be given to apply a temporal filter.
    """
    csw = CatalogueServiceWeb(endpoint, timeout=timeout)
    filter_list = build_filter(text=text, bbox=bbox, start=start, stop=stop, crs=crs)
    raw_records = _get_records(csw, filter_list, pagesize=pagesize, maxrecords=maxrecords)
    return [_to_record(r) for r in raw_records.values()]


def search_with_feature_type(endpoint: str, *, probe: bool = True, **kwargs) -> list[CswRecord]:
    """Run :func:`search`, keeping only records that resolve to a featureType.

    Each returned record has its ``feature_type`` populated. ``probe`` controls
    the dataset-probe fallback (see :func:`resolve_feature_type`).
    """
    matched: list[CswRecord] = []
    for record in search(endpoint, **kwargs):
        ft = resolve_feature_type(record, probe=probe)
        if ft:
            record.feature_type = ft
            matched.append(record)
    return matched
