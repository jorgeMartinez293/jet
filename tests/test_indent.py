from jet import indent


def test_leading_whitespace():
    assert indent.leading_whitespace("    foo") == "    "
    assert indent.leading_whitespace("\t\tfoo") == "\t\t"
    assert indent.leading_whitespace("foo") == ""


def test_python_indent_after_colon():
    assert indent.compute_newline_indent("def foo():", "python") == "    "
    assert indent.compute_newline_indent("    if x:", "python") == "        "


def test_python_indent_after_open_paren():
    assert indent.compute_newline_indent("foo(", "python") == "    "
    assert indent.compute_newline_indent("    bar([", "python") == "        "


def test_python_dedent_after_return():
    assert indent.compute_newline_indent("    return x", "python") == ""
    assert indent.compute_newline_indent("        pass", "python") == "    "


def test_python_preserve_indent_default():
    assert indent.compute_newline_indent("    x = 1", "python") == "    "


def test_non_python_generic():
    assert indent.compute_newline_indent("    foo {", None) == "        "
    assert indent.compute_newline_indent("    foo", None) == "    "


def test_should_open_block():
    assert indent.should_open_block("foo{", "}") is True
    assert indent.should_open_block("foo[", "]") is True
    assert indent.should_open_block("foo(", ")") is True
    assert indent.should_open_block("foo{", "x") is False
    assert indent.should_open_block("foo", "}") is False


def test_strip_inline_comment_ignores_colon_in_string():
    # Colon inside a string should not trigger indent.
    assert indent.compute_newline_indent('x = "value:"', "python") == ""
