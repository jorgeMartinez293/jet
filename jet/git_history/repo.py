"""Subprocess-backed git data layer for the history sidebar.

All `git` invocations live here. The rest of the package operates on the
dataclasses this module returns.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

_GIT_TIMEOUT = 5.0


@dataclass(frozen=True)
class Commit:
    sha: str
    short: str
    parents: tuple[str, ...]
    author: str
    timestamp: int
    subject: str


@dataclass(frozen=True)
class Ref:
    name: str
    kind: Literal["local", "remote", "tag"]
    target_sha: str


@dataclass(frozen=True)
class CommitStats:
    files_changed: int
    insertions: int
    deletions: int
    per_file: tuple[tuple[str, int, int], ...]


class Repo:
    """Light wrapper around `git` for the workspace at `workspace`."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)

    # ------------------------------------------------------------------ helpers

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.workspace), *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if result.returncode != 0:
            raise _GitError(result.stderr.strip() or "git command failed")
        return result.stdout

    # ------------------------------------------------------------------ public

    def is_git_repo(self) -> bool:
        try:
            self._run("rev-parse", "--git-dir")
            return True
        except (_GitError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def head(self) -> tuple[str, str | None]:
        sha = self._run("rev-parse", "HEAD").strip()
        try:
            name = self._run("symbolic-ref", "--short", "HEAD").strip()
            return sha, name
        except _GitError:
            return sha, None


class _GitError(RuntimeError):
    """Internal — `git` returned non-zero."""
