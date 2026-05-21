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


def test_wmsloader_load_populates_crs_picker_and_default(monkeypatch):
    monkeypatch.setattr(
        "common.wms.list_layers",
        lambda url: ([("temp", "T")], "1.1.1", "Demo", ["EPSG:32661", "EPSG:4326", "EPSG:5041"]),
    )
    loader = WmsLoader(get_map=lambda: None)
    loader.url_input.value = "http://example.org/wms"
    loader.load()
    assert list(loader.crs_select.options) == ["EPSG:32661", "EPSG:4326", "EPSG:5041"]
    assert loader.crs_select.value == "EPSG:4326"  # prefers 4326 when available
    assert loader.crs_select.visible


def test_wmsloader_resolve_crs_used_for_picked_crs(monkeypatch):
    monkeypatch.setattr(
        "common.wms.list_layers", lambda url: ([("temp", "T")], "1.1.1", "Demo", ["EPSG:4326", "EPSG:32661"])
    )
    added = []
    fake_map = SimpleNamespace(add_layer=added.append)
    sentinel_crs = {"name": "EPSG:32661"}
    loader = WmsLoader(get_map=lambda: fake_map, resolve_crs=lambda epsg: sentinel_crs)
    loader.url_input.value = "http://example.org/wms"
    loader.load()
    loader.crs_select.value = "EPSG:32661"
    loader.layer_select.value = ["temp"]
    loader.add_selected()
    assert len(added) == 1
    assert added[0].crs == sentinel_crs


def test_wmsloader_on_add_receives_layer_instead_of_map(monkeypatch):
    monkeypatch.setattr(
        "common.wms.list_layers", lambda url: ([("temp", "T")], "1.1.1", "Demo", ["EPSG:4326"])
    )
    map_added = []
    hooked = []
    fake_map = SimpleNamespace(add_layer=map_added.append)
    loader = WmsLoader(get_map=lambda: fake_map, on_add=lambda layer, name: hooked.append((layer, name)))
    loader.url_input.value = "http://example.org/wms"
    loader.load()
    loader.layer_select.value = ["temp"]
    loader.add_selected()
    assert map_added == []                 # on_add owns placement now
    assert len(hooked) == 1 and hooked[0][1] == "temp"


def test_wmsloader_resolve_crs_none_shows_message_and_skips(monkeypatch):
    monkeypatch.setattr(
        "common.wms.list_layers", lambda url: ([("temp", "T")], "1.1.1", "Demo", ["EPSG:32662"])
    )
    added = []
    fake_map = SimpleNamespace(add_layer=added.append)
    loader = WmsLoader(get_map=lambda: fake_map, resolve_crs=lambda epsg: None)
    loader.url_input.value = "http://example.org/wms"
    loader.load()
    loader.crs_select.value = "EPSG:32662"
    loader.layer_select.value = ["temp"]
    loader.add_selected()
    assert added == []            # nothing added for an unsupported CRS
    assert loader.error.visible   # message shown
    assert loader.layer_select.visible  # pickers stay so user can choose again


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
