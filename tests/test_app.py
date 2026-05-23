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


@pytest.mark.asyncio
async def test_sidebar_cycle_includes_git_in_repo(tmp_path: Path):
    from tests.git_history.fixtures.make_repo import commit, init_repo
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    f = repo_path / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        # tree → git
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is False
        assert app.query_one("#sidebar-git").display is True
        assert app.query_one("#sidebar-settings").display is False
        # git → settings
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-git").display is False
        assert app.query_one("#sidebar-settings").display is True
        # settings → tree
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is True


@pytest.mark.asyncio
async def test_sidebar_cycle_skips_git_outside_repo(tmp_path: Path):
    """When workspace is not a git repo the git sidebar is removed from cycle."""
    from textual.css.query import NoMatches
    f = tmp_path / "x.py"
    f.write_text("a=1\n")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        # Either #sidebar-git doesn't exist or is permanently hidden.
        try:
            git_w = app.query_one("#sidebar-git")
            assert git_w.display is False
        except NoMatches:
            pass
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-settings").display is True


@pytest.mark.asyncio
async def test_shift_tab_opens_commit_buffer(tmp_path: Path):
    from textual.widgets import TabbedContent, TabPane
    from tests.git_history.fixtures.make_repo import commit, init_repo
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init", content="a\n")
    commit(repo_path, "second", content="a\nb\n")
    f = repo_path / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        # Cycle to git sidebar, then focus its widget.
        await pilot.press("ctrl+b")
        from jet.git_history.widget import GitHistoryWidget
        git_w = app.query_one(GitHistoryWidget)
        git_w.focus()
        await pilot.pause()
        await pilot.press("shift+tab")
        await pilot.pause()
        tabs = app.query_one(TabbedContent)
        panes = list(tabs.query(TabPane))
        # A new tab with a `<commit:` title should now exist.
        titles = [str(tabs.get_tab(p.id).label) for p in panes if p.id]
        assert any("commit:" in t for t in titles)


@pytest.mark.asyncio
async def test_popup_visible_only_while_git_focused(tmp_path: Path):
    from jet.git_history.widget import GitHistoryWidget
    from jet.git_history.popup import CommitDetailPopup
    from tests.git_history.fixtures.make_repo import commit, init_repo
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    commit(repo_path, "second")
    f = repo_path / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")  # show git sidebar
        git_w = app.query_one(GitHistoryWidget)
        git_w.focus()
        await pilot.pause()
        popup = app.query_one(CommitDetailPopup)
        assert popup.display is True
        # Focus the editor — popup should hide.
        ed = app._active_editor()
        assert ed is not None
        ed.focus()
        await pilot.pause()
        assert popup.display is False
