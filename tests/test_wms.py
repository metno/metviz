from types import SimpleNamespace

from common.wms import WmsLoader, list_layers, wms_base_url
from ipyleaflet import projections


def test_wms_base_url_strips_getcapabilities_control_params():
    assert (
        wms_base_url("https://adc-wms.met.no/get_wms/abc/wms?SERVICE=WMS&REQUEST=GetCapabilities")
        == "https://adc-wms.met.no/get_wms/abc/wms"
    )
    # keeps non-control params (e.g. an access token), drops service/request/version
    assert (
        wms_base_url("https://x/wms?service=WMS&request=GetCapabilities&version=1.3.0&token=abc")
        == "https://x/wms?token=abc"
    )
    # a bare endpoint is unchanged
    assert wms_base_url("https://x/wms") == "https://x/wms"


class _FakeLayer:
    def __init__(self, title, crs=None):
        self.title = title
        self.crsOptions = crs or []


class _FakeWMS:
    contents = {
        "temp": _FakeLayer("Temperature", ["EPSG:4326", "EPSG:3857"]),
        "wind": _FakeLayer("", ["EPSG:4326"]),
    }
    version = "1.3.0"
    identification = SimpleNamespace(title="Demo WMS")


def test_list_layers(monkeypatch):
    monkeypatch.setattr("owslib.wms.WebMapService", lambda url: _FakeWMS())
    layers, version, title, crs = list_layers("http://example.org/wms")
    assert ("temp", "Temperature") in layers
    assert ("wind", "") in layers
    assert version == "1.3.0"
    assert title == "Demo WMS"
    assert crs == ["EPSG:3857", "EPSG:4326"]  # sorted union across layers


def test_wmsloader_load_populates_picker(monkeypatch):
    monkeypatch.setattr(
        "common.wms.list_layers", lambda url: ([("temp", "Temperature")], "1.3.0", "Demo", ["EPSG:4326"])
    )
    loader = WmsLoader(get_map=lambda: None)
    loader.url_input.value = "http://example.org/wms"
    loader.load()
    # CheckBoxGroup value is the layer name, not the (buggy) 2nd character.
    assert loader.layer_select.options == {"temp: Temperature": "temp"}
    assert loader.layer_select.visible and loader.add_button.visible
    assert not loader.error.visible
    assert loader.crs_options == ["EPSG:4326"]


def test_wmsloader_on_layer_crs_called_before_add(monkeypatch):
    monkeypatch.setattr(
        "common.wms.list_layers", lambda url: ([("temp", "Temperature")], "1.3.0", "Demo", ["EPSG:4326"])
    )
    seen = []
    added = []
    fake_map = SimpleNamespace(add_layer=added.append)
    loader = WmsLoader(get_map=lambda: fake_map, on_layer_crs=seen.append)
    loader.url_input.value = "http://example.org/wms"
    loader.load()
    loader.layer_select.value = ["temp"]
    loader.add_selected()
    assert seen == [["EPSG:4326"]]   # hook got the supported CRS list
    assert len(added) == 1


def test_wmsloader_load_empty_url_shows_error():
    loader = WmsLoader(get_map=lambda: None)
    loader.url_input.value = "   "
    loader.load()
    assert loader.error.visible
    assert not loader.add_button.visible


def test_wmsloader_add_selected_adds_layer_with_crs():
    added = []
    fake_map = SimpleNamespace(add_layer=added.append)
    loader = WmsLoader(get_map=lambda: fake_map, get_crs=lambda: projections.EPSG3857)
    loader.url_input.value = "http://example.org/wms"
    loader.layer_select.options = {"temp: Temperature": "temp"}
    loader.layer_select.value = ["temp"]
    loader.add_selected()
    assert len(added) == 1
    assert added[0].layers == "temp"
    assert added[0].crs == projections.EPSG3857
