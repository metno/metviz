from common.logging_utils import create_logger
from common.widgets import build_metadata_widget, show_hide_widget


class _Toggle:
    def __init__(self, visible: bool):
        self.visible = visible


def test_show_hide_toggles_target():
    target = _Toggle(visible=True)
    show_hide_widget(widget=target)
    assert target.visible is False
    show_hide_widget(widget=target)
    assert target.visible is True


def test_show_hide_hides_peer_when_revealed():
    target = _Toggle(visible=False)
    peer = _Toggle(visible=True)
    show_hide_widget(widget=target, hide=peer)
    assert target.visible is True
    assert peer.visible is False


def test_show_hide_reveals_peer_when_hidden():
    target = _Toggle(visible=True)
    peer = _Toggle(visible=False)
    show_hide_widget(widget=target, reveal=peer)
    assert target.visible is False
    assert peer.visible is True


def test_build_metadata_widget_returns_hidden_layout_and_button():
    layout, button = build_metadata_widget({"title": "Demo", "featureType": "timeSeries"})
    assert layout.visible is False
    assert "Demo" in layout.text


def test_create_logger_is_idempotent():
    logger = create_logger("metviz.test")
    count = len(logger.handlers)
    create_logger("metviz.test")
    assert len(logger.handlers) == count
