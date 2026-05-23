"""Sticky one-line header above the git history widget that shows lane labels."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from .layout import GraphGrid

_LANE_WIDTH = 2  # glyph + space, matches widget render


class BranchHeader(Static):
    DEFAULT_CSS = """
    BranchHeader {
        dock: top;
        height: 1;
        background: transparent;
        color: #7f8a99;
        padding: 0;
    }
    """

    grid: reactive[GraphGrid | None] = reactive(None)

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)

    def watch_grid(self, _old, _new) -> None:
        if self.is_mounted:
            self.update(self.render_to_text())

    def render_to_text(self) -> str:
        grid = self.grid
        if grid is None or not grid.lane_to_branch:
            return ""
        labeled = sorted(grid.lane_to_branch.items())
        total = max(lane * _LANE_WIDTH + len(name) for lane, name in labeled)
        out: list[str] = [" "] * total
        for i, (lane, name) in enumerate(labeled):
            start = lane * _LANE_WIDTH
            if i + 1 < len(labeled):
                avail = labeled[i + 1][0] * _LANE_WIDTH - start - 1
            else:
                avail = total - start
            if avail <= 0:
                continue
            label = name if len(name) <= avail else name[: max(0, avail - 1)] + "…"
            for j, ch in enumerate(label):
                if start + j < len(out):
                    out[start + j] = ch
        return "".join(out).rstrip()

    def render(self) -> Text:
        return Text(self.render_to_text())
