from common.basemap import land_geojson


def test_land_geojson_loads_multipolygon():
    data = land_geojson()
    assert data["type"] == "FeatureCollection"
    geom = data["features"][0]["geometry"]
    assert geom["type"] == "MultiPolygon"
    assert len(geom["coordinates"]) > 100  # detailed regional coastline


def _covers(polys, lat, lon):
    for poly in polys:
        ring = poly[0]
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        if min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys):
            return True
    return False


def test_land_geojson_covers_svalbard_mainland_and_jan_mayen():
    polys = land_geojson()["features"][0]["geometry"]["coordinates"]
    assert _covers(polys, 78, 16)     # Svalbard
    assert _covers(polys, 60, 7)      # mainland Norway
    assert _covers(polys, 71, -8.5)   # Jan Mayen


def test_land_geojson_clipped_to_region():
    # No coordinates should fall far outside the Norway+Svalbard clip box.
    polys = land_geojson()["features"][0]["geometry"]["coordinates"]
    for poly in polys:
        for ring in poly:
            for lon, lat in ring:
                assert -12.001 <= lon <= 36.001
                assert 56.0 <= lat <= 82.001
