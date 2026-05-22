"""Fuzzy file finder — walks workspace, respects .gitignore, ranks with rapidfuzz."""

from __future__ import annotations

from pathlib import Path

import pathspec
from rapidfuzz import fuzz


_DEFAULT_IGNORES: tuple[str, ...] = (
    ".git/",
    "__pycache__/",
    ".venv/",
    "venv/",
    "node_modules/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "*.pyc",
    ".DS_Store",
)


def _load_gitignore(root: Path) -> pathspec.PathSpec:
    patterns: list[str] = list(_DEFAULT_IGNORES)
    gi = root / ".gitignore"
    if gi.is_file():
        try:
            patterns.extend(gi.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            pass
    return pathspec.PathSpec.from_lines("gitignore", patterns)


def list_files(root: Path, limit: int = 5000) -> list[Path]:
    """Return up to `limit` files under root, respecting .gitignore + defaults."""
    spec = _load_gitignore(root)
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        rel_str = str(rel)
        if spec.match_file(rel_str):
            continue
        out.append(path)
        if len(out) >= limit:
            break
    return out


def rank(query: str, files: list[Path], root: Path, limit: int = 50) -> list[Path]:
    """Return top `limit` files ranked by fuzzy match against `query`.

    Empty query returns the first `limit` files unchanged (useful for initial display).
    """
    if not query:
        return files[:limit]
    scored: list[tuple[int, Path]] = []
    q = query.lower()
    for f in files:
        rel = str(f.relative_to(root))
        score = fuzz.WRatio(q, rel.lower())
        # Boost matches in the basename.
        score += fuzz.partial_ratio(q, f.name.lower()) // 4
        scored.append((score, f))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [f for _, f in scored[:limit]]
