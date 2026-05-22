"""Map file extensions to tree-sitter languages supported by Textual's TextArea."""

from __future__ import annotations

from pathlib import Path


_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".regex": "regex",
    ".xml": "xml",
}


def detect_language(path: str | Path) -> str | None:
    """Return tree-sitter language id for a path, or None if unknown."""
    suffix = Path(path).suffix.lower()
    return _EXT_TO_LANG.get(suffix)
