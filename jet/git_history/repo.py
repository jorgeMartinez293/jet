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

    _LOG_SEP = "\x1f"  # ASCII unit separator — never appears in author/subject

    def log(self, limit: int = 500, skip: int = 0) -> list[Commit]:
        try:
            out = self._run(
                "log",
                "--all",
                f"--pretty=format:%H{self._LOG_SEP}%h{self._LOG_SEP}%P{self._LOG_SEP}%an <%ae>{self._LOG_SEP}%at{self._LOG_SEP}%s",
                f"-n{limit}",
                f"--skip={skip}",
            )
        except _GitError:
            return []
        result: list[Commit] = []
        for line in out.splitlines():
            if not line:
                continue
            parts = line.split(self._LOG_SEP)
            if len(parts) != 6:
                continue
            sha, short, parents_field, author, ts, subject = parts
            parents = tuple(p for p in parents_field.split() if p)
            result.append(
                Commit(
                    sha=sha,
                    short=short,
                    parents=parents,
                    author=author,
                    timestamp=int(ts),
                    subject=subject,
                )
            )
        return result

    def refs(self) -> list[Ref]:
        try:
            out = self._run(
                "for-each-ref",
                f"--format=%(refname){self._LOG_SEP}%(objectname)",
                "refs/heads",
                "refs/remotes",
                "refs/tags",
            )
        except _GitError:
            return []
        result: list[Ref] = []
        for line in out.splitlines():
            if not line:
                continue
            try:
                refname, target = line.split(self._LOG_SEP)
            except ValueError:
                continue
            kind: Literal["local", "remote", "tag"]
            if refname.startswith("refs/heads/"):
                kind = "local"
                name = refname[len("refs/heads/"):]
            elif refname.startswith("refs/remotes/"):
                kind = "remote"
                name = refname[len("refs/remotes/"):]
            elif refname.startswith("refs/tags/"):
                kind = "tag"
                name = refname[len("refs/tags/"):]
            else:
                continue
            result.append(Ref(name=name, kind=kind, target_sha=target))
        return result

    def is_dirty(self) -> bool:
        try:
            out = self._run("status", "--porcelain", "--untracked-files=no")
        except _GitError:
            return False
        for line in out.splitlines():
            if line.strip():
                return True
        return False

    def stats(self, sha: str) -> CommitStats:
        return self._stats_cached(sha)

    @lru_cache(maxsize=1024)
    def _stats_cached(self, sha: str) -> CommitStats:
        try:
            out = self._run("diff-tree", "--numstat", "--no-commit-id", "-r", sha)
        except _GitError:
            return CommitStats(0, 0, 0, ())
        per_file: list[tuple[str, int, int]] = []
        insertions = deletions = 0
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            ins_s, del_s, *path_parts = parts
            path = "\t".join(path_parts)
            ins = 0 if ins_s == "-" else int(ins_s)
            dels = 0 if del_s == "-" else int(del_s)
            insertions += ins
            deletions += dels
            per_file.append((path, ins, dels))
        return CommitStats(
            files_changed=len(per_file),
            insertions=insertions,
            deletions=deletions,
            per_file=tuple(per_file),
        )

    def full_message(self, sha: str) -> str:
        return self._full_message_cached(sha)

    @lru_cache(maxsize=128)
    def _full_message_cached(self, sha: str) -> str:
        try:
            return self._run("show", "-s", "--format=%B", sha).rstrip("\n")
        except _GitError:
            return ""

    def status_diff_stat(self) -> str:
        try:
            status = self._run("status", "--short")
        except _GitError:
            status = ""
        try:
            stat = self._run("diff", "--stat")
        except _GitError:
            stat = ""
        return f"{status}\n{stat}".strip()

    def refresh(self) -> None:
        """Drop all caches."""
        self._stats_cached.cache_clear()
        self._full_message_cached.cache_clear()


class _GitError(RuntimeError):
    """Internal — `git` returned non-zero."""
