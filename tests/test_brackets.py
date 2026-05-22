from jet import brackets


def test_closer_for():
    assert brackets.closer_for("(") == ")"
    assert brackets.closer_for("[") == "]"
    assert brackets.closer_for("{") == "}"
    assert brackets.closer_for('"') == '"'
    assert brackets.closer_for("'") == "'"
    assert brackets.closer_for("`") == "`"
    assert brackets.closer_for("x") is None


def test_should_auto_close_basic():
    assert brackets.should_auto_close("", 0, "(") is True
    assert brackets.should_auto_close("def foo", 7, "(") is True


def test_should_auto_close_blocks_when_next_is_word():
    # Cursor before identifier — don't auto-close, would shadow the text.
    assert brackets.should_auto_close("foo bar", 0, "(") is False


def test_should_auto_close_quote_after_identifier():
    # Don't insert closing quote when previous char is alnum (apostrophe in word).
    assert brackets.should_auto_close("don", 3, "'") is False


def test_should_skip_over_close_pair():
    # Cursor at '|)' and user types ')' — should skip.
    assert brackets.should_skip_over("()", 1, ")") is True
    # But typing ']' next to ')' should not skip.
    assert brackets.should_skip_over("()", 1, "]") is False


def test_should_delete_pair_on_empty():
    # Cursor between empty pair `(|)`.
    assert brackets.should_delete_pair("()", 1) is True
    # Not adjacent.
    assert brackets.should_delete_pair("ab", 1) is False
    # Out of range.
    assert brackets.should_delete_pair("()", 0) is False
    assert brackets.should_delete_pair("()", 2) is False
