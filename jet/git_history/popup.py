"""Floating mini-popup for the current commit."""

from __future__ import annotations

import textwrap

from rich.text import Text
from textual.widgets import Static

from .repo import Commit, CommitStats


class CommitDetailPopup(Static):
    """2-line floating box near the cursor commit."""

    DEFAULT_CSS = """
    CommitDetailPopup {
        width: 32;
        height: 4;
        border: round #cdd6f4;
        background: #1e1e2e;
        color: #cdd6f4;
        display: none;
        padding: 0 1;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._commit: Commit | None = None
        self._stats: CommitStats | None = None

    def set_commit(self, commit: Commit | None, stats: CommitStats | None) -> None:
        self._commit = commit
        self._stats = stats
        if self.is_mounted:
            self.update(self._render_body())

    def render(self) -> Text:
        return self._render_body()

    def _render_body(self) -> Text:
        if self._commit is None:
            return Text("", end="")
        if self._stats is None:
            line1 = Text("…", style="dim")
        else:
            line1 = Text(f"+{self._stats.insertions} / -{self._stats.deletions}")
        subject = textwrap.shorten(self._commit.subject, width=30, placeholder="…")
        line2 = Text(subject)
        body = Text()
        body.append_text(line1)
        body.append("\n")
        body.append_text(line2)
        return body
