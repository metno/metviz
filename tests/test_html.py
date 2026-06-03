from common.html import dict_to_html, dict_to_html_ul


def test_dict_to_html_simple():
    out = dict_to_html({"title": "X"})
    assert "<b>title</b>: X" in out


def test_dict_to_html_nested():
    out = dict_to_html({"a": {"b": 2}})
    assert "<b>a</b>" in out and "<b>b</b>: 2" in out


def test_dict_to_html_list_value():
    assert "[1, 2]" in dict_to_html({"vals": [1, 2]})


def test_dict_to_html_ul_structure():
    out = dict_to_html_ul({"a": 1})
    assert out.startswith("<ul>") and out.endswith("</ul>")
    assert "<li><b>a</b>: 1</li>" in out
