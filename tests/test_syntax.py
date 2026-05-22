from jet.syntax import detect_language


def test_python_extensions():
    assert detect_language("foo.py") == "python"
    assert detect_language("foo.pyi") == "python"


def test_js_family():
    assert detect_language("a.js") == "javascript"
    assert detect_language("a.tsx") == "javascript"


def test_unknown_returns_none():
    assert detect_language("foo.unknown") is None
    assert detect_language("LICENSE") is None
