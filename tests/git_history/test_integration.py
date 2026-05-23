"""End-to-end: build a multi-branch fixture repo, drive the app, assert state."""

from __future__ import annotations

from pathlib import Path

import pytest

from jet.app import JetApp
from jet.git_history.popup import CommitDetailPopup
from jet.git_history.widget import GitHistoryWidget
from tests.git_history.fixtures.make_repo import (
    branch,
    checkout,
    commit,
    init_repo,
    merge,
    tag,
)


@pytest.mark.asyncio
async def test_navigate_branched_history(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "main-1")
    branch(repo, "feature")
    # Feature touches its own file so the later merge is conflict-free.
    commit(repo, "feat-1", file="feature.txt")
    commit(repo, "feat-2", file="feature.txt")
    checkout(repo, "main")
    commit(repo, "main-2")
    merge(repo, "feature")
    tag(repo, "v1.0")
    f = repo / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")  # show git sidebar
        git_w = app.query_one(GitHistoryWidget)
        git_w.focus()
        await pilot.pause()
        assert git_w.grid is not None
        assert git_w.grid.num_lanes >= 2
        # Walk down a few commits.
        head_sha = git_w.cursor_sha
        await pilot.press("shift+down")
        await pilot.press("shift+down")
        await pilot.pause()
        assert git_w.cursor_sha != head_sha
        # Pop the commit buffer with Shift+Tab.
        await pilot.press("shift+tab")
        await pilot.pause()
        from textual.widgets import TabbedContent, TabPane
        tabs = app.query_one(TabbedContent)
        titles = [str(tabs.get_tab(p.id).label) for p in tabs.query(TabPane) if p.id]
        assert any("commit:" in t for t in titles)
        # Popup is visible while git widget has focus.
        git_w.focus()
        await pilot.pause()
        popup = app.query_one(CommitDetailPopup)
        assert popup.display is True
