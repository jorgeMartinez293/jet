"""File tree sidebar — DirectoryTree subclass that hides dotfiles by default."""

from __future__ import annotations

from pathlib import Path

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

    ICON_NODE = "  "
    ICON_NODE_EXPANDED = "  "
    ICON_FILE = ""

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
        scrollbar-background: transparent;
        scrollbar-color: #3a3f4b;
        scrollbar-size: 1 1;
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

    def filter_paths(self, paths):  # type: ignore[override]
        return [p for p in paths if not self._hidden(p)]

    @staticmethod
    def _hidden(path: Path) -> bool:
        name = path.name
        if name in _HIDE_NAMES:
            return True
        if name.startswith(".") and name not in (".env",):
            return True
        return False
