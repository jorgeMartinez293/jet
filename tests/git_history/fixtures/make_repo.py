"""Test helper that scripts real git repos in a tmp_path."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """Run a git command inside *repo*; raise CalledProcessError with stderr on failure."""
    cmd = ["git", "-C", str(repo), *args]
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=merged_env)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr
        )
    return result.stdout


def init_repo(path: Path) -> Path:
    """Init a repo with deterministic identity. Returns the path."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True, text=True)
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
    """Create a new branch *name* and immediately switch to it."""
    _git(repo, "checkout", "-q", "-b", name)


def checkout(repo: Path, name: str) -> None:
    """Switch the working tree to an existing branch or commit *name*."""
    _git(repo, "checkout", "-q", name)


def merge(repo: Path, name: str, *, message: str | None = None) -> str:
    """Merge branch *name* into the current branch with a no-ff merge commit; return short sha."""
    msg = message or f"Merge branch '{name}'"
    _git(repo, "merge", "-q", "--no-ff", "-m", msg, name)
    return _git(repo, "rev-parse", "--short", "HEAD").strip()


def tag(repo: Path, name: str, *, sha: str | None = None) -> None:
    """Create a lightweight tag *name*, optionally pointing at *sha*."""
    args = ["tag", name]
    if sha is not None:
        args.append(sha)
    _git(repo, *args)
