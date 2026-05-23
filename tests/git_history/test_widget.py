"""Widget tests using Textual pilot."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from jet.git_history.widget import GitHistoryWidget
from tests.git_history.fixtures.make_repo import branch, checkout, commit, init_repo, merge


class _Host(App):
    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self._workspace = workspace

    def compose(self) -> ComposeResult:
        yield GitHistoryWidget(self._workspace, id="git")


@pytest.mark.asyncio
async def test_widget_loads_grid_on_mount(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "first")
    commit(repo, "second")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None
        assert len(w.grid.rows) == 2
        assert w.cursor_sha is not None  # initial cursor on HEAD


@pytest.mark.asyncio
async def test_cursor_up_moves_to_older_commit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "first")
    commit(repo, "second")
    commit(repo, "third")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None
        head_sha = w.grid.rows[0].commit.sha
        assert w.cursor_sha == head_sha
        w.action_cursor_down()  # toward older commits
        assert w.cursor_sha == w.grid.rows[1].commit.sha
        w.action_cursor_down()
        assert w.cursor_sha == w.grid.rows[2].commit.sha
        w.action_cursor_up()
        assert w.cursor_sha == w.grid.rows[1].commit.sha


@pytest.mark.asyncio
async def test_cursor_right_jumps_to_sibling_lane(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "base")
    branch(repo, "feature")
    commit(repo, "feat")
    checkout(repo, "main")
    commit(repo, "main2")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None and w.grid.num_lanes >= 2
        start_lane = next(r.lane for r in w.grid.rows if r.commit and r.commit.sha == w.cursor_sha)
        w.action_cursor_right()
        new_lane = next(r.lane for r in w.grid.rows if r.commit and r.commit.sha == w.cursor_sha)
        assert new_lane != start_lane


@pytest.mark.asyncio
async def test_commit_focused_message_posted_on_move(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "a")
    commit(repo, "b")
    received: list[GitHistoryWidget.CommitFocused] = []

    class _Capture(_Host):
        def on_git_history_widget_commit_focused(self, ev: GitHistoryWidget.CommitFocused) -> None:
            received.append(ev)

    app = _Capture(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        w.action_cursor_down()
        await pilot.pause()
        assert received, "expected a CommitFocused message"


@pytest.mark.asyncio
async def test_infinite_scroll_loads_more(tmp_path: Path, monkeypatch) -> None:
    repo = init_repo(tmp_path / "r")
    for i in range(8):
        commit(repo, f"c{i}")
    # Patch initial limit to 3 so we can exercise pagination.
    import jet.git_history.widget as widget_mod
    monkeypatch.setattr(widget_mod, "_INITIAL_LIMIT", 3)
    monkeypatch.setattr(widget_mod, "_PAGE_SIZE", 3)
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None and len(w.grid.rows) == 3
        # Step cursor down past the loaded slice.
        for _ in range(5):
            w.action_cursor_down()
        await pilot.pause()
        assert w.grid is not None
        assert len(w.grid.rows) > 3


from jet.git_history.popup import CommitDetailPopup
from jet.git_history.repo import Commit, CommitStats


def test_popup_renders_stats_and_truncated_subject() -> None:
    c = Commit(
        sha="a" * 40,
        short="a" * 7,
        parents=(),
        author="x",
        timestamp=0,
        subject="this is a very long subject line that should be truncated nicely",
    )
    popup = CommitDetailPopup()
    popup.set_commit(c, stats=CommitStats(1, 12, 3, ()))
    rendered = popup.render()
    text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
    assert "+12 / -3" in text
    assert "this is a very long subject" in text
    # Truncated to 30 chars with ellipsis somewhere.
    assert "…" in text or "..." in text


@pytest.mark.asyncio
async def test_branch_header_shows_main_label(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "init")
    commit(repo, "second")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        from jet.git_history.branch_header import BranchHeader
        header = app.query_one(BranchHeader)
        assert "main" in header.render_to_text()
