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

from .branch_header import BranchHeader
from .layout import GraphGrid, GraphRow, build_grid
from .repo import Repo

_INITIAL_LIMIT = 500
_PAGE_SIZE = 500
_LOAD_AHEAD_ROWS = 5


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
        "guide": Style(color="#585b70"),
    }

    def __init__(self, workspace: Path, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.workspace = Path(workspace)
        self.repo = Repo(self.workspace)
        self._commits_loaded = 0
        self._all_commits: list = []

    def compose(self):
        yield BranchHeader(id="git-branch-header")

    def on_mount(self) -> None:
        self._load()

    # ------------------------------------------------------------------ data

    def _load(self) -> None:
        if not self.repo.is_git_repo():
            self.grid = None
            return
        commits = self.repo.log(limit=_INITIAL_LIMIT)
        self._all_commits = commits
        self._commits_loaded = len(commits)
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        if not self._all_commits:
            self.grid = None
            return
        refs = self.repo.refs()
        head_sha, head_branch = self.repo.head()
        dirty = self.repo.is_dirty()
        self.grid = build_grid(self._all_commits, refs, head_sha, head_branch, dirty)
        if self.cursor_sha is None and head_sha:
            self.cursor_sha = head_sha
        rows = len(self.grid.rows)
        cols = max(1, self.grid.num_lanes * 2 - 1)
        self.virtual_size = Size(cols, rows)
        self.styles.width = max(12, min(60, self.grid.num_lanes * 2 + 4))
        from textual.css.query import NoMatches
        try:
            header = self.query_one(BranchHeader)
        except NoMatches:
            header = None
        if header is not None:
            header.grid = self.grid

    def on_click(self, event) -> None:
        if self.grid is None:
            return
        _, scroll_y = self.scroll_offset
        row_idx = event.y + scroll_y
        if not (0 <= row_idx < len(self.grid.rows)):
            return
        row = self.grid.rows[row_idx]
        if row.commit is None:
            return
        self._update_cursor(row)

    def action_refresh_repo(self) -> None:
        self.repo.refresh()
        self._load()
        self.refresh()

    # ------------------------------------------------------------------ nav

    def _current_row_idx(self) -> int | None:
        if self.grid is None or self.cursor_sha is None:
            return None
        return self.grid.sha_to_row.get(self.cursor_sha)

    def action_cursor_down(self) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            for r in self.grid.rows:
                if r.commit is not None:
                    self._update_cursor(r)
                    break
            self._maybe_load_more()
            return
        current_lane = self.grid.rows[idx].lane
        moved = False
        for j in range(idx + 1, len(self.grid.rows)):
            row = self.grid.rows[j]
            if row.commit is not None and row.lane == current_lane:
                self._update_cursor(row)
                moved = True
                break
        if not moved:
            for j in range(idx + 1, len(self.grid.rows)):
                row = self.grid.rows[j]
                if row.commit is not None:
                    self._update_cursor(row)
                    break
        self._maybe_load_more()

    def _maybe_load_more(self) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            return
        if idx >= len(self.grid.rows) - _LOAD_AHEAD_ROWS:
            more = self.repo.log(limit=_PAGE_SIZE, skip=len(self._all_commits))
            if not more:
                return
            self._all_commits = self._all_commits + more
            old_cursor = self.cursor_sha
            self._rebuild_grid()
            self.cursor_sha = old_cursor
            self.refresh()

    def action_cursor_up(self) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            return
        current_lane = self.grid.rows[idx].lane
        for j in range(idx - 1, -1, -1):
            row = self.grid.rows[j]
            if row.commit is not None and row.lane == current_lane:
                self._update_cursor(row)
                return
        for j in range(idx - 1, -1, -1):
            row = self.grid.rows[j]
            if row.commit is not None:
                self._update_cursor(row)
                return

    def action_cursor_right(self) -> None:
        self._jump_lane(direction=+1)

    def action_cursor_left(self) -> None:
        self._jump_lane(direction=-1)

    def _jump_lane(self, *, direction: int) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            return
        current_lane = self.grid.rows[idx].lane
        used_lanes = sorted({r.lane for r in self.grid.rows if r.commit is not None})
        if direction > 0:
            candidates = [l for l in used_lanes if l > current_lane]
        else:
            candidates = [l for l in reversed(used_lanes) if l < current_lane]
        for target_lane in candidates:
            for row in self.grid.rows:
                if row.commit is not None and row.lane == target_lane:
                    self._update_cursor(row)
                    return

    def _update_cursor(self, row: GraphRow) -> None:
        if row.commit is None:
            return
        self.cursor_sha = row.commit.sha
        self.refresh()
        self._post_focus(row)
        self._ensure_visible(row)

    def _post_focus(self, row: GraphRow) -> None:
        idx = self.grid.sha_to_row.get(row.commit.sha) if (self.grid and row.commit) else None
        self.post_message(self.CommitFocused(sha=row.commit.sha if row.commit else None, row=idx or 0))

    def _ensure_visible(self, row: GraphRow) -> None:
        idx = self.grid.sha_to_row.get(row.commit.sha) if (self.grid and row.commit) else None
        if idx is None:
            return
        _, scroll_y = self.scroll_offset
        viewport = self.size.height
        if idx < scroll_y:
            self.scroll_to(y=idx, animate=False)
        elif idx >= scroll_y + viewport:
            self.scroll_to(y=max(0, idx - viewport + 1), animate=False)

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
