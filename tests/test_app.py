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
