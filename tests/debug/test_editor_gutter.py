from jet.editor import JetEditor


def test_editor_starts_with_empty_breakpoints():
    ed = JetEditor(text="a=1\nb=2\n")
    assert ed.breakpoints == frozenset()
    assert ed.current_exec_line is None


def test_editor_set_breakpoints():
    ed = JetEditor(text="a=1\nb=2\n")
    ed.set_breakpoints({1, 3})
    assert ed.breakpoints == frozenset({1, 3})


def test_editor_set_current_exec_line():
    ed = JetEditor(text="a=1\nb=2\n")
    ed.set_current_exec_line(2)
    assert ed.current_exec_line == 2
    ed.set_current_exec_line(None)
    assert ed.current_exec_line is None


def test_editor_read_only_toggle():
    ed = JetEditor(text="a=1\n")
    assert ed.read_only is False
    ed.read_only = True
    assert ed.read_only is True


def test_gutter_breakpoint_marker_present_without_line_numbers():
    from jet.settings_panel import EditorConfig
    cfg = EditorConfig(show_line_numbers=False)
    ed = JetEditor(text="a=1\nb=2\n", config=cfg)
    ed.set_breakpoints({1})
    marker = ed.gutter_marker_for_line(1)
    assert marker is not None
    assert "●" in marker.plain


def test_gutter_current_line_marker():
    from jet.settings_panel import EditorConfig
    cfg = EditorConfig(show_line_numbers=False)
    ed = JetEditor(text="a=1\nb=2\n", config=cfg)
    ed.set_current_exec_line(2)
    marker = ed.gutter_marker_for_line(2)
    assert marker is not None
    assert "▶" in marker.plain


def test_gutter_returns_none_for_unmarked_line():
    ed = JetEditor(text="a=1\nb=2\n")
    assert ed.gutter_marker_for_line(99) is None
