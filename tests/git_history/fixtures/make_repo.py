"""Test helper that scripts real git repos in a tmp_path."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    cmd = ["git", "-C", str(repo), *args]
    merged_env = {**os.environ, **(env or {})}
    return subprocess.check_output(cmd, text=True, env=merged_env)


def init_repo(path: Path) -> Path:
    """Init a repo with deterministic identity. Returns the path."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["git", "init", "-q", "-b", "main", str(path)])
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "commit.gpgsign", "false")
    return path


def commit(repo: Path, message: str, *, file: str = "file.txt", content: str | None = None) -> str:
    """Write `content` (or append a line) to `file`, commit, return short sha."""
    fp = repo / file
    if content is None:
        existing = fp.read_text() if fp.exists() else ""
        content = existing + f"{message}\n"
    fp.write_text(content)
    _git(repo, "add", str(fp))
    env = {
        "GIT_AUTHOR_DATE": "2026-01-01T12:00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T12:00:00",
    }
    _git(repo, "commit", "-q", "-m", message, env=env)
    return _git(repo, "rev-parse", "--short", "HEAD").strip()


def branch(repo: Path, name: str) -> None:
    _git(repo, "checkout", "-q", "-b", name)


def checkout(repo: Path, name: str) -> None:
    _git(repo, "checkout", "-q", name)


def merge(repo: Path, name: str, *, message: str | None = None) -> str:
    msg = message or f"Merge branch '{name}'"
    _git(repo, "merge", "-q", "--no-ff", "-m", msg, name)
    return _git(repo, "rev-parse", "--short", "HEAD").strip()


def tag(repo: Path, name: str, *, sha: str | None = None) -> None:
    args = ["tag", name]
    if sha is not None:
        args.append(sha)
    _git(repo, *args)
