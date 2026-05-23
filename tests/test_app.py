"""Integration test — boot the app, type into editor, verify autoclose + indent."""

from __future__ import annotations

from pathlib import Path

import pytest

from jet.app import JetApp
from jet.editor import JetEditor


@pytest.mark.asyncio
async def test_app_opens_python_file_with_highlight(tmp_path: Path):
    f = tmp_path / "hello.py"
    f.write_text("print('hi')\n")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app._active_editor()
        assert ed is not None
        assert ed.path == f.resolve()
        assert ed.language == "python"
        assert ed.text == "print('hi')\n"


@pytest.mark.asyncio
async def test_autoclose_paren(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app._active_editor()
        assert isinstance(ed, JetEditor)
        ed.focus()
        await pilot.press("(")
        await pilot.pause()
        assert ed.text == "()"
        assert ed.cursor_location == (0, 1)


@pytest.mark.asyncio
async def test_autoindent_after_colon(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app._active_editor()
        assert isinstance(ed, JetEditor)
        ed.focus()
        for ch in "def foo":
            await pilot.press(ch)
        await pilot.press("(")  # autocloses to ()
        await pilot.press("right")  # move past )
        await pilot.press(":")
        await pilot.press("enter")
        await pilot.pause()
        assert ed.text == "def foo():\n    "
        assert ed.cursor_location == (1, 4)


@pytest.mark.asyncio
async def test_backspace_deletes_pair(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app._active_editor()
        assert isinstance(ed, JetEditor)
        ed.focus()
        await pilot.press("(")
        await pilot.pause()
        assert ed.text == "()"
        await pilot.press("backspace")
        await pilot.pause()
        assert ed.text == ""


@pytest.mark.asyncio
async def test_save_writes_file(tmp_path: Path):
    f = tmp_path / "out.py"
    f.write_text("")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app._active_editor()
        assert isinstance(ed, JetEditor)
        ed.focus()
        for ch in "x=1":
            await pilot.press(ch)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert f.read_text() == "x=1"


@pytest.mark.asyncio
async def test_rebound_tab_switch_overrides_editor(tmp_path: Path):
    """Rebinding next_tab to a key the editor normally claims must still switch tabs."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("a=1\n")
    b.write_text("b=2\n")
    app = JetApp(paths=[a, b])
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        tabs = app.query_one(TabbedContent)
        # b.py opened last → active.
        active_before = tabs.active
        # Rebind next_tab to ctrl+right (TextArea normally consumes this for word jump).
        app.set_keymap({"next_tab": "ctrl+right", "prev_tab": "ctrl+left"})
        ed = app._active_editor()
        assert ed is not None
        ed.focus()
        await pilot.press("ctrl+right")
        await pilot.pause()
        assert tabs.active != active_before


@pytest.mark.asyncio
async def test_sidebar_cycle_tree_settings(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("a=1\n")
    app = JetApp([f])
    async with app.run_test() as pilot:
        # Starts on tree. One cycle hides tree and shows settings.
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is False
        assert app.query_one("#sidebar-settings").display is True
        # Next cycle wraps back to tree.
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is True
        assert app.query_one("#sidebar-settings").display is False


@pytest.mark.asyncio
async def test_editor_read_only_blocks_insertion(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("hello\n")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app._active_editor()
        assert ed is not None
        ed.read_only = True
        ed.focus()
        await pilot.press("a")
        await pilot.pause()
        assert ed.text == "hello\n"
