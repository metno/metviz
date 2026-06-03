from common.layer_manager import LayerManager


class _FakeLayer:
    def __init__(self, name):
        self.name = name
        self.opacity = 1.0


class _FakeMap:
    """Records add/remove and keeps an ordered layer list like ipyleaflet."""

    def __init__(self):
        self.layers = []

    def add_layer(self, layer):
        self.layers.append(layer)

    def remove_layer(self, layer):
        # ipyleaflet raises if absent; mimic a no-op-on-present removal
        self.layers = [x for x in self.layers if x is not layer]


def _names(m):
    return [x.name for x in m.layers]


def test_add_registers_and_adds_to_map():
    m = _FakeMap()
    lm = LayerManager(get_map=lambda: m)
    a = _FakeLayer("A")
    lm.add(a, "A")
    assert _names(m) == ["A"]
    assert lm.empty.visible is False


def test_newest_layer_is_on_top():
    # list is top->bottom; map draw order is bottom->top, so newest (A) added
    # last == on top == end of the map's layer list.
    m = _FakeMap()
    lm = LayerManager(get_map=lambda: m)
    first = _FakeLayer("first")
    second = _FakeLayer("second")
    lm.add(first, "first")
    lm.add(second, "second")
    assert _names(m) == ["first", "second"]  # second drawn last (on top)


def test_move_reorders_draw_stack():
    m = _FakeMap()
    lm = LayerManager(get_map=lambda: m)
    a = _FakeLayer("A")
    b = _FakeLayer("B")
    lm.add(a, "A")          # list: [A]
    lm.add(b, "B")          # list: [B, A]  (B on top) -> map [A, B]
    lm.move(a, -1)          # move A up -> list [A, B] -> map [B, A]
    assert _names(m) == ["B", "A"]


def test_set_opacity_sets_layer_opacity():
    m = _FakeMap()
    lm = LayerManager(get_map=lambda: m)
    a = _FakeLayer("A")
    lm.add(a, "A")
    lm.set_opacity(a, 0.3)
    assert a.opacity == 0.3


def test_set_visible_removes_and_restores():
    m = _FakeMap()
    lm = LayerManager(get_map=lambda: m)
    a = _FakeLayer("A")
    lm.add(a, "A")
    lm.set_visible(a, False)
    assert _names(m) == []
    lm.set_visible(a, True)
    assert _names(m) == ["A"]


def test_remove_drops_layer():
    m = _FakeMap()
    lm = LayerManager(get_map=lambda: m)
    a = _FakeLayer("A")
    lm.add(a, "A")
    lm.remove(a)
    assert _names(m) == []
    assert lm.empty.visible is True


def test_clear_forgets_all():
    m = _FakeMap()
    lm = LayerManager(get_map=lambda: m)
    lm.add(_FakeLayer("A"), "A")
    lm.clear()
    assert lm.empty.visible is True
    assert lm._entries == []
