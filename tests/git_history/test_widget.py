"""Widget tests using Textual pilot."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from jet.git_history.widget import GitHistoryWidget
from tests.git_history.fixtures.make_repo import commit, init_repo


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
