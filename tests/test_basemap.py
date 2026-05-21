from common.basemap import _max_lat, land_geojson


def test_land_geojson_loads_feature_collection():
    data = land_geojson()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0


def test_land_geojson_min_lat_filters_southern_features():
    full = land_geojson()
    northern = land_geojson(min_lat=20)
    assert 0 < len(northern["features"]) < len(full["features"])
    # every kept feature reaches at least 20N
    for f in northern["features"]:
        assert _max_lat(f["geometry"]["coordinates"]) >= 20


def test_max_lat_handles_nested_coordinates():
    # a single Polygon ring
    assert _max_lat([[[0.0, 10.0], [1.0, 70.0], [2.0, 5.0]]]) == 70.0
