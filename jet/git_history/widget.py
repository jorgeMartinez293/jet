"""GitHistoryWidget — Textual ScrollView rendering a GraphGrid."""

from __future__ import annotations

from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.strip import Strip

from .layout import GraphGrid, build_grid
from .repo import Repo


class GitHistoryWidget(ScrollView):
    """Read-only commit-graph sidebar."""

    DEFAULT_CSS = """
    GitHistoryWidget {
        background: transparent;
        background-tint: transparent;
        color: #cdd6f4;
        border-right: solid white;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-size: 0 0;
        min-width: 12;
        max-width: 60;
        width: 18;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_repo", show=False),
    ]

    grid: reactive[GraphGrid | None] = reactive(None)
    cursor_sha: reactive[str | None] = reactive(None)

    class CommitFocused(Message):
        def __init__(self, sha: str | None, row: int) -> None:
            super().__init__()
            self.sha = sha
            self.row = row

    _STYLES = {
        "branch": Style(color="#cdd6f4"),
        "head": Style(color="#f9e2af", bold=True),
        "tagged": Style(color="#94e2d5"),
        "dirty": Style(color="#f9e2af"),
        "guide": Style(color="#2a2f3a"),
    }

    def __init__(self, workspace: Path, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.workspace = Path(workspace)
        self.repo = Repo(self.workspace)
        self._commits_loaded = 0

    def on_mount(self) -> None:
        self._load()

    # ------------------------------------------------------------------ data

    def _load(self) -> None:
        if not self.repo.is_git_repo():
            self.grid = None
            return
        commits = self.repo.log(limit=500)
        self._commits_loaded = len(commits)
        refs = self.repo.refs()
        head_sha, head_branch = self.repo.head() if commits else ("", None)
        dirty = self.repo.is_dirty() if commits else False
        self.grid = build_grid(commits, refs, head_sha, head_branch, dirty)
        if self.cursor_sha is None and head_sha:
            self.cursor_sha = head_sha
        rows = len(self.grid.rows)
        cols = self.grid.num_lanes * 2 + 1
        self.virtual_size = Size(cols, rows)
        self.styles.width = max(12, min(60, self.grid.num_lanes * 2 + 4))

    def action_refresh_repo(self) -> None:
        self.repo.refresh()
        self._load()
        self.refresh()

    # ------------------------------------------------------------------ render

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        row_idx = y + scroll_y
        if self.grid is None or row_idx >= len(self.grid.rows):
            return Strip.blank(self.size.width)
        row = self.grid.rows[row_idx]
        segments: list[Segment] = []
        for lane_idx, cell in enumerate(row.cells):
            style = self._STYLES.get(cell.style, self._STYLES["branch"])
            if (
                self.cursor_sha is not None
                and row.commit is not None
                and row.commit.sha == self.cursor_sha
                and lane_idx == row.lane
            ):
                style = style + Style(reverse=True)
            segments.append(Segment(cell.glyph, style))
            if lane_idx < len(row.cells) - 1:
                segments.append(Segment(" ", self._STYLES["guide"]))
        strip = Strip(segments)
        strip = strip.crop(scroll_x, scroll_x + self.size.width)
        return strip
