"""File tree sidebar — DirectoryTree subclass that hides dotfiles by default."""

from __future__ import annotations

from pathlib import Path

from rich.style import Style
from textual import on
from textual.reactive import reactive
from textual.widgets import DirectoryTree


_HIDE_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
        ".DS_Store",
        ".idea",
        ".vscode",
    }
)


class JetTree(DirectoryTree):
    """DirectoryTree filtered to hide noise (dot-folders, caches, vendored deps)."""

    # No chevrons. guide_depth=3 → "├─ name" (short bar + space before label).
    ICON_NODE = ""
    ICON_NODE_EXPANDED = ""
    ICON_FILE = ""

    guide_depth = 3

    MIN_WIDTH = 18
    MAX_WIDTH = 60

    DEFAULT_CSS = """
    JetTree {
        width: 28;
        min-width: 18;
        max-width: 60;
        background: transparent;
        background-tint: transparent;
        color: #cdd6f4;
        padding: 0 1;
        border-right: solid white;
        overflow-x: hidden;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }
    JetTree:focus {
        background-tint: transparent;
    }
    JetTree > .tree--guides {
        color: #2a2f3a;
        background: transparent;
    }
    JetTree > .tree--guides-hover,
    JetTree > .tree--guides-selected {
        color: #4a525e;
        background: transparent;
    }
    JetTree > .tree--cursor {
        background: transparent;
        color: #ffffff;
        text-style: reverse;
    }
    JetTree:focus > .tree--cursor {
        background: transparent;
        color: #ffffff;
        text-style: reverse;
    }
    JetTree > .tree--highlight {
        background: transparent;
        color: #ffffff;
    }
    JetTree > .tree--highlight-line {
        background: transparent;
    }
    JetTree > .tree--label {
        color: #cdd6f4;
    }
    """

    moving_path: reactive[Path | None] = reactive(None)

    def watch_moving_path(self, _old: Path | None, _new: Path | None) -> None:
        self.refresh()

    def render_label(self, node, base_style, style):  # type: ignore[override]
        text = super().render_label(node, base_style, style)
        if self.moving_path is not None and node.data is not None and node.data.path == self.moving_path:
            text.stylize(Style(color="#1e1e2e", bgcolor="#f9e2af", bold=True))
        return text

    def filter_paths(self, paths):  # type: ignore[override]
        return [p for p in paths if not self._hidden(p)]

    def on_mount(self) -> None:
        self.call_after_refresh(self._recompute_width)

    @on(DirectoryTree.NodeExpanded)
    def _on_expanded_resize(self, _event: DirectoryTree.NodeExpanded) -> None:
        self.call_after_refresh(self._recompute_width)

    @on(DirectoryTree.NodeCollapsed)
    def _on_collapsed_resize(self, _event: DirectoryTree.NodeCollapsed) -> None:
        self.call_after_refresh(self._recompute_width)

    def _recompute_width(self) -> None:
        max_cells = 0

        def walk(node, depth: int) -> None:
            nonlocal max_cells
            label = node.label
            label_cells = label.cell_len if hasattr(label, "cell_len") else len(str(label))
            # guide_depth chars per indent level + label (icons are empty)
            cells = depth * self.guide_depth + label_cells
            if cells > max_cells:
                max_cells = cells
            if node.is_expanded:
                for child in node.children:
                    walk(child, depth + 1)

        walk(self.root, 0)
        # +2 horizontal padding, +1 border-right, +1 safety
        total = max_cells + 4
        total = max(self.MIN_WIDTH, min(self.MAX_WIDTH, total))
        self.styles.width = total

    @staticmethod
    def _hidden(path: Path) -> bool:
        name = path.name
        if name in _HIDE_NAMES:
            return True
        if name.startswith(".") and name not in (".env",):
            return True
        return False
