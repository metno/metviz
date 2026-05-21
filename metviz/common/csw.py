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
from dataclasses import dataclass, field

from owslib import fes
from owslib.csw import CatalogueServiceWeb
from owslib.fes import SortBy, SortProperty

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


@dataclass
class CswRecord:
    """A trimmed-down CSW metadata record."""

    identifier: str
    title: str
    references: list = field(default_factory=list)
    subjects: list = field(default_factory=list)
    feature_type: str | None = None

    @property
    def opendap_url(self) -> str | None:
        return extract_opendap_url(self.references)


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


def _to_record(raw) -> CswRecord:
    return CswRecord(
        identifier=getattr(raw, "identifier", "") or "",
        title=getattr(raw, "title", "") or "",
        references=list(getattr(raw, "references", []) or []),
        subjects=list(getattr(raw, "subjects", []) or []),
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
        )
        records.update(csw.records)
        nextrecord = csw.results.get("nextrecord", 0)
        if not nextrecord or len(records) >= maxrecords:
            break
        startposition = nextrecord
    return records


def build_filter(*, text=None, bbox=None, start=None, stop=None, crs: str = DEFAULT_CRS):
    """Build the FES filter list for a CSW query (no network).

    Returns a list suitable for ``getrecords2(constraints=...)``. Crucially,
    ``fes.And`` / ``fes.Or`` require **at least two** operands, so a single
    free-text term is passed through un-wrapped and a lone constraint is not
    wrapped in an ``And``. An empty query returns ``[]`` (match everything).
    """
    constraints = []

    if text:
        terms = [text] if isinstance(text, str) else list(text)
        kw = dict(wildCard="*", escapeChar="\\", singleChar="?", propertyname="apiso:AnyText")
        likes = [fes.PropertyIsLike(literal=f"*{t}*", **kw) for t in terms]
        constraints.append(fes.Or(likes) if len(likes) > 1 else likes[0])

    if start is not None and stop is not None:
        begin, end = fes_date_filter(start, stop)
        constraints += [begin, end]

    if bbox:
        constraints.append(fes.BBox(bbox, crs=crs))

    if len(constraints) >= 2:
        return [fes.And(constraints)]
    return constraints


def connect(endpoint: str, timeout: int = 60) -> CatalogueServiceWeb:
    """Open a CSW connection (fetches GetCapabilities once).

    Reuse the returned object across page requests so capabilities are not
    re-fetched on every page turn.
    """
    return CatalogueServiceWeb(endpoint, timeout=timeout)


def get_page(csw, filter_list, *, startposition: int = 1, pagesize: int = 10):
    """Fetch one page of CSW records.

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
    )
    records = [_to_record(r) for r in csw.records.values()]
    return records, dict(csw.results)


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
