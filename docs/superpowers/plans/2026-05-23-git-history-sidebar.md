# Git History Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `git` sidebar to `jet` that shows the repository's commit graph centred on main, with focus-bound mini popup, sticky branch labels and a Shift+Tab read-only commit-detail buffer.

**Architecture:** Three-layer split. `repo.py` runs `git` via subprocess and returns dataclasses. `layout.py` is a pure function that turns commits+refs into a 2D `GraphGrid`. `widget.py` renders the grid using Textual's `ScrollView.render_line`. Two satellite widgets (`popup.py`, `branch_header.py`) decorate. A new `commit_view.format_commit` produces plain-text for the detail buffer, opened in `JetEditor` with a new `read_only=True` flag.

**Tech Stack:** Python 3.11+, Textual ≥0.85, pytest + pytest-asyncio, subprocess `git`.

**Spec:** `docs/superpowers/specs/2026-05-23-git-history-sidebar-design.md`

---

## File Structure

**New files:**

```
jet/git_history/
  __init__.py                 # public re-exports
  repo.py                     # Repo + Commit/Ref/CommitStats dataclasses
  layout.py                   # build_grid + GraphGrid/GraphRow/GraphCell
  widget.py                   # GitHistoryWidget (ScrollView)
  popup.py                    # CommitDetailPopup (Static, screen-level)
  branch_header.py            # BranchHeader (Static, sticky lane labels)
  commit_view.py              # format_commit(repo, sha) -> str

tests/git_history/
  __init__.py
  fixtures/
    __init__.py
    make_repo.py              # helper to build real git repos in tmp_path
  test_repo.py
  test_layout.py
  test_widget.py
  test_commit_view.py
  test_integration.py
```

**Modified files:**

- `jet/app.py` — `SIDEBAR_ORDER`, `compose`, `on_mount`, `action_sidebar_*`, `action_move_toggle`, popup sync, message handler.
- `jet/editor.py` — accept `read_only=True` and gate save.
- `jet/styles.tcss` — selectors for `#sidebar-git`, `#commit-popup`, `BranchHeader`.
- `tests/test_app.py` — extend `test_sidebar_cycle_tree_settings` to also exercise the git slot (or add a new test).

---

## Task 1: Scaffold package + fixtures

**Files:**
- Create: `jet/git_history/__init__.py`
- Create: `tests/git_history/__init__.py`
- Create: `tests/git_history/fixtures/__init__.py`
- Create: `tests/git_history/fixtures/make_repo.py`

- [ ] **Step 1: Create empty package modules**

```bash
mkdir -p jet/git_history tests/git_history/fixtures
```

Write `jet/git_history/__init__.py`:

```python
"""Git history sidebar package."""
```

Write `tests/git_history/__init__.py` and `tests/git_history/fixtures/__init__.py` as empty files.

- [ ] **Step 2: Write `make_repo.py` fixture helper**

Write `tests/git_history/fixtures/make_repo.py`:

```python
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
```

- [ ] **Step 3: Smoke-test the fixture**

Write `tests/git_history/test_repo.py` (placeholder smoke test, removed in Task 2):

```python
from __future__ import annotations

from pathlib import Path

from tests.git_history.fixtures.make_repo import branch, commit, init_repo, merge, tag


def test_fixture_builds_branched_history(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "init")
    commit(repo, "second")
    branch(repo, "feature")
    commit(repo, "feat work")
    branch(repo, "main")  # error: branch already exists
```

Run: `pytest tests/git_history/test_repo.py -v`
Expected: FAIL with "already exists" — confirms the helper invokes git.

- [ ] **Step 4: Replace with a passing smoke test**

Rewrite `tests/git_history/test_repo.py`:

```python
from __future__ import annotations

from pathlib import Path

from tests.git_history.fixtures.make_repo import branch, checkout, commit, init_repo, merge, tag


def test_fixture_builds_branched_history(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "init")
    commit(repo, "second")
    branch(repo, "feature")
    commit(repo, "feat work")
    checkout(repo, "main")
    sha_merge = merge(repo, "feature")
    tag(repo, "v1.0")
    assert sha_merge  # got a sha
    assert (repo / ".git").is_dir()
```

Run: `pytest tests/git_history/test_repo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/__init__.py tests/git_history/__init__.py tests/git_history/fixtures/ tests/git_history/test_repo.py
git commit -m "feat(git-history): scaffold package and test fixtures"
```

---

## Task 2: Repo dataclasses + `is_git_repo` + `head`

**Files:**
- Create: `jet/git_history/repo.py`
- Modify: `tests/git_history/test_repo.py`

- [ ] **Step 1: Write failing tests for is_git_repo / head**

Append to `tests/git_history/test_repo.py`:

```python
from jet.git_history.repo import Repo


def test_is_git_repo_true_for_real_repo(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    assert Repo(repo_path).is_git_repo() is True


def test_is_git_repo_false_for_non_repo(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert Repo(tmp_path / "empty").is_git_repo() is False


def test_head_returns_sha_and_branch(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    sha, branch_name = Repo(repo_path).head()
    assert len(sha) == 40
    assert branch_name == "main"


def test_head_detached_returns_none_branch(tmp_path: Path) -> None:
    from tests.git_history.fixtures.make_repo import _git
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "first")
    commit(repo_path, "second")
    first = _git(repo_path, "rev-parse", "HEAD~1").strip()
    _git(repo_path, "checkout", "-q", first)
    sha, branch_name = Repo(repo_path).head()
    assert sha == first
    assert branch_name is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/git_history/test_repo.py -v`
Expected: FAIL with `ImportError: cannot import name 'Repo'`.

- [ ] **Step 3: Implement Repo with is_git_repo + head**

Write `jet/git_history/repo.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/git_history/test_repo.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/repo.py tests/git_history/test_repo.py
git commit -m "feat(git-history): Repo.is_git_repo + Repo.head"
```

---

## Task 3: `Repo.log` + `Repo.refs`

**Files:**
- Modify: `jet/git_history/repo.py`
- Modify: `tests/git_history/test_repo.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/git_history/test_repo.py`:

```python
def test_log_returns_commits_newest_first(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "first")
    commit(repo_path, "second")
    commit(repo_path, "third")
    commits = Repo(repo_path).log(limit=10)
    assert [c.subject for c in commits] == ["third", "second", "first"]
    assert all(len(c.sha) == 40 and len(c.short) == 7 for c in commits)
    assert commits[0].parents == (commits[1].sha,)
    assert commits[2].parents == ()


def test_log_respects_limit_and_skip(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    for i in range(5):
        commit(repo_path, f"c{i}")
    page1 = Repo(repo_path).log(limit=2)
    page2 = Repo(repo_path).log(limit=2, skip=2)
    assert [c.subject for c in page1] == ["c4", "c3"]
    assert [c.subject for c in page2] == ["c2", "c1"]


def test_log_includes_all_branches(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "main-1")
    branch(repo_path, "feature")
    commit(repo_path, "feat-1")
    checkout(repo_path, "main")
    commit(repo_path, "main-2")
    subjects = {c.subject for c in Repo(repo_path).log(limit=10)}
    assert subjects == {"main-1", "feat-1", "main-2"}


def test_refs_local_remote_tag(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    branch(repo_path, "feature")
    checkout(repo_path, "main")
    tag(repo_path, "v0.1")
    refs = Repo(repo_path).refs()
    kinds = {(r.name, r.kind) for r in refs}
    assert ("main", "local") in kinds
    assert ("feature", "local") in kinds
    assert ("v0.1", "tag") in kinds


def test_refs_in_empty_repo(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    assert Repo(repo_path).refs() == []
```

- [ ] **Step 2: Run tests, expect AttributeError**

Run: `pytest tests/git_history/test_repo.py -v`
Expected: FAIL with `AttributeError: 'Repo' object has no attribute 'log'`.

- [ ] **Step 3: Implement `log` and `refs`**

Append the following methods to the `Repo` class in `jet/git_history/repo.py` (before the trailing `_GitError` definition):

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/git_history/test_repo.py -v`
Expected: PASS (9 tests total).

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/repo.py tests/git_history/test_repo.py
git commit -m "feat(git-history): Repo.log + Repo.refs"
```

---

## Task 4: `Repo.is_dirty` + `Repo.stats` + `Repo.full_message` + `Repo.status_diff_stat`

**Files:**
- Modify: `jet/git_history/repo.py`
- Modify: `tests/git_history/test_repo.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/git_history/test_repo.py`:

```python
def test_is_dirty_false_clean(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    assert Repo(repo_path).is_dirty() is False


def test_is_dirty_true_with_modified(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    (repo_path / "file.txt").write_text("changed\n")
    assert Repo(repo_path).is_dirty() is True


def test_stats_for_commit(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init", content="a\nb\nc\n")
    sha = commit(repo_path, "edit", content="a\nB\nc\nd\n")
    long_sha = (repo_path / ".git" / "HEAD")  # placeholder, will read via Repo
    repo = Repo(repo_path)
    full_sha, _ = repo.head()
    stats = repo.stats(full_sha)
    assert stats.files_changed == 1
    assert stats.insertions == 2  # "B" and "d"
    assert stats.deletions == 1  # "b"
    assert stats.per_file == (("file.txt", 2, 1),)


def test_full_message_returns_complete_body(tmp_path: Path) -> None:
    from tests.git_history.fixtures.make_repo import _git
    repo_path = init_repo(tmp_path / "r")
    (repo_path / "f.txt").write_text("x\n")
    _git(repo_path, "add", "f.txt")
    _git(repo_path, "commit", "-q", "-m", "subject line\n\nbody paragraph here")
    repo = Repo(repo_path)
    sha, _ = repo.head()
    msg = repo.full_message(sha)
    assert msg.startswith("subject line")
    assert "body paragraph here" in msg


def test_status_diff_stat_includes_status(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init", content="a\n")
    (repo_path / "file.txt").write_text("a\nb\n")
    output = Repo(repo_path).status_diff_stat()
    assert "file.txt" in output
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/git_history/test_repo.py -v`
Expected: FAIL with attribute errors for `is_dirty`, `stats`, etc.

- [ ] **Step 3: Implement remaining Repo methods + caches**

Append to the `Repo` class in `jet/git_history/repo.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/git_history/test_repo.py -v`
Expected: PASS (14 tests total).

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/repo.py tests/git_history/test_repo.py
git commit -m "feat(git-history): Repo.is_dirty/stats/full_message/status_diff_stat"
```

---

## Task 5: Layout dataclasses + `build_grid` for linear history

**Files:**
- Create: `jet/git_history/layout.py`
- Create: `tests/git_history/test_layout.py`

- [ ] **Step 1: Write failing test for linear history**

Write `tests/git_history/test_layout.py`:

```python
"""Pure-function tests for layout.build_grid."""

from __future__ import annotations

from jet.git_history.layout import GraphGrid, build_grid
from jet.git_history.repo import Commit, Ref


def _c(sha: str, parents: tuple[str, ...] = (), subject: str = "") -> Commit:
    return Commit(
        sha=sha * 5,
        short=sha,
        parents=tuple(p * 5 for p in parents),
        author="t",
        timestamp=0,
        subject=subject or sha,
    )


def test_linear_history_single_lane() -> None:
    c3 = _c("c3", ("c2",))
    c2 = _c("c2", ("c1",))
    c1 = _c("c1", ())
    refs = [Ref(name="main", kind="local", target_sha=c3.sha)]
    grid = build_grid([c3, c2, c1], refs, head_sha=c3.sha, head_branch="main", dirty=False)
    assert isinstance(grid, GraphGrid)
    assert grid.num_lanes == 1
    assert grid.main_lane == 0
    assert len(grid.rows) == 3
    assert all(row.lane == 0 for row in grid.rows)
    assert grid.rows[0].glyph_kind == "head"
    assert grid.rows[1].glyph_kind == "normal"
    assert grid.rows[2].glyph_kind == "normal"
    assert grid.sha_to_row[c3.sha] == 0
    assert grid.sha_to_row[c1.sha] == 2
```

- [ ] **Step 2: Run test, expect ImportError**

Run: `pytest tests/git_history/test_layout.py -v`
Expected: FAIL with `ImportError: cannot import name 'GraphGrid'`.

- [ ] **Step 3: Implement minimal layout (dataclasses + linear case)**

Write `jet/git_history/layout.py`:

```python
"""Pure functions that assign lanes and glyphs for the git graph sidebar."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .repo import Commit, Ref

GlyphKind = Literal["normal", "head", "tagged", "dirty"]

_MAIN_CANDIDATES: tuple[str, ...] = ("main", "master", "trunk")


@dataclass(frozen=True)
class GraphCell:
    glyph: str
    style: str


@dataclass(frozen=True)
class GraphRow:
    commit: Commit | None
    lane: int
    glyph_kind: GlyphKind
    cells: tuple[GraphCell, ...]
    refs: tuple[Ref, ...]
    branch_label: str | None


@dataclass(frozen=True)
class GraphGrid:
    rows: tuple[GraphRow, ...]
    num_lanes: int
    main_lane: int
    sha_to_row: dict[str, int]
    lane_to_branch: dict[int, str]


# --------------------------------------------------------------------- build


def build_grid(
    commits: list[Commit],
    refs: list[Ref],
    head_sha: str,
    head_branch: str | None,
    dirty: bool = False,
) -> GraphGrid:
    """Turn newest-first commits + refs into a renderable GraphGrid."""
    if not commits:
        return GraphGrid(rows=(), num_lanes=1, main_lane=0, sha_to_row={}, lane_to_branch={})

    main_branch_name = _choose_main_branch(refs, head_branch)
    tag_targets = {r.target_sha for r in refs if r.kind == "tag"}
    refs_by_sha: dict[str, list[Ref]] = {}
    for r in refs:
        refs_by_sha.setdefault(r.target_sha, []).append(r)

    raw_rows, lane_to_branch = _assign_lanes(commits, refs, main_branch_name, head_sha)

    # Centre main lane.
    main_lane_raw = lane_to_branch_lane(lane_to_branch, main_branch_name)
    if main_lane_raw is None:
        main_lane_raw = raw_rows[0].lane

    used = sorted({row.lane for row in raw_rows})
    half = max(main_lane_raw - used[0], used[-1] - main_lane_raw)
    num_lanes = 2 * half + 1
    centre = half  # zero-based index of main in the recentred grid
    shift = centre - main_lane_raw

    rows: list[GraphRow] = []
    sha_to_row: dict[str, int] = {}
    shifted_lane_to_branch = {lane + shift: name for lane, name in lane_to_branch.items()}

    for idx, raw in enumerate(raw_rows):
        new_lane = raw.lane + shift
        commit = raw.commit
        if commit is None:
            kind: GlyphKind = "dirty"
        elif commit.sha == head_sha:
            kind = "head"
        elif commit.sha in tag_targets:
            kind = "tagged"
        else:
            kind = "normal"
        cells = _row_cells(num_lanes, new_lane, kind)
        commit_refs = tuple(refs_by_sha.get(commit.sha, [])) if commit else ()
        branch_label = _branch_label_for_row(idx, raw_rows, raw, shifted_lane_to_branch.get(new_lane))
        rows.append(
            GraphRow(
                commit=commit,
                lane=new_lane,
                glyph_kind=kind,
                cells=cells,
                refs=commit_refs,
                branch_label=branch_label,
            )
        )
        if commit is not None:
            sha_to_row[commit.sha] = idx

    return GraphGrid(
        rows=tuple(rows),
        num_lanes=num_lanes,
        main_lane=centre,
        sha_to_row=sha_to_row,
        lane_to_branch=shifted_lane_to_branch,
    )


# --------------------------------------------------------------------- helpers


@dataclass
class _RawRow:
    commit: Commit | None
    lane: int


def _choose_main_branch(refs: list[Ref], head_branch: str | None) -> str | None:
    local_names = {r.name for r in refs if r.kind == "local"}
    for candidate in _MAIN_CANDIDATES:
        if candidate in local_names:
            return candidate
    return head_branch


def lane_to_branch_lane(lane_to_branch: dict[int, str], branch_name: str | None) -> int | None:
    if branch_name is None:
        return None
    for lane, name in lane_to_branch.items():
        if name == branch_name:
            return lane
    return None


def _assign_lanes(
    commits: list[Commit],
    refs: list[Ref],
    main_branch: str | None,
    head_sha: str,
) -> tuple[list[_RawRow], dict[int, str]]:
    """Single-pass lane assignment. Returns rows + lane→branch name map."""
    # active_lanes: lane_index → expected SHA for the next commit on that lane.
    active_lanes: dict[int, str] = {}
    lane_to_branch: dict[int, str] = {}
    rows: list[_RawRow] = []

    # Seed the main lane (lane 0) so it always exists.
    main_target_sha: str | None = None
    for r in refs:
        if r.kind == "local" and main_branch is not None and r.name == main_branch:
            main_target_sha = r.target_sha
            break
    if main_target_sha is not None:
        active_lanes[0] = main_target_sha
        lane_to_branch[0] = main_branch  # type: ignore[assignment]
    else:
        # No main branch found; HEAD will seed the only lane.
        active_lanes[0] = head_sha

    new_lane_counter = 0  # used to alternate L/R when opening additional lanes

    for commit in commits:
        # Pick this commit's lane.
        matching_lanes = [lane for lane, sha in active_lanes.items() if sha == commit.sha]
        if matching_lanes:
            # Prefer main lane (0) if among matches.
            lane = 0 if 0 in matching_lanes else matching_lanes[0]
            for extra in matching_lanes:
                if extra != lane:
                    del active_lanes[extra]
        else:
            lane = _open_new_lane(active_lanes, new_lane_counter)
            new_lane_counter += 1

        # Update lane state for parents.
        if commit.parents:
            active_lanes[lane] = commit.parents[0]
            for extra_parent in commit.parents[1:]:
                # Reuse if another lane already expects this sha; else allocate.
                reused = next((l for l, s in active_lanes.items() if s == extra_parent and l != lane), None)
                if reused is None:
                    new_lane = _open_new_lane(active_lanes, new_lane_counter)
                    new_lane_counter += 1
                    active_lanes[new_lane] = extra_parent
        else:
            active_lanes.pop(lane, None)

        rows.append(_RawRow(commit=commit, lane=lane))

    return rows, lane_to_branch


def _open_new_lane(active: dict[int, str], counter: int) -> int:
    """Pick the first unused lane, alternating +1, -1, +2, -2, … from 0."""
    candidates: list[int] = [0]
    step = 1
    while len(candidates) < counter + 32:
        candidates.append(step)
        candidates.append(-step)
        step += 1
    for c in candidates:
        if c not in active:
            return c
    raise RuntimeError("no lane slot available")


def _row_cells(num_lanes: int, dot_lane: int, kind: GlyphKind) -> tuple[GraphCell, ...]:
    glyph = {"head": "★", "tagged": "◆", "dirty": "✱", "normal": "●"}[kind]
    style = {"head": "head", "tagged": "tagged", "dirty": "dirty", "normal": "branch"}[kind]
    cells: list[GraphCell] = []
    for lane in range(num_lanes):
        if lane == dot_lane:
            cells.append(GraphCell(glyph=glyph, style=style))
        else:
            cells.append(GraphCell(glyph=" ", style="guide"))
    return tuple(cells)


def _branch_label_for_row(
    idx: int,
    raw_rows: list[_RawRow],
    raw: _RawRow,
    branch_name: str | None,
) -> str | None:
    if branch_name is None or raw.commit is None:
        return None
    # Branch label only on the first (topmost) row of that lane.
    if any(prev.lane == raw.lane for prev in raw_rows[:idx]):
        return None
    return branch_name
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/git_history/test_layout.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/layout.py tests/git_history/test_layout.py
git commit -m "feat(git-history): GraphGrid dataclasses + linear-history layout"
```

---

## Task 6: Layout — branch + merge + multiple tips

**Files:**
- Modify: `tests/git_history/test_layout.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/git_history/test_layout.py`:

```python
def test_feature_branch_with_merge() -> None:
    # History (newest first):
    #   m2 — merge of feat into main
    #   f1 — feature commit
    #   m1 — main commit (parent of both f1 and m2's first parent)
    m2 = _c("m2", ("m1", "f1"))
    f1 = _c("f1", ("m1",))
    m1 = _c("m1", ())
    refs = [Ref(name="main", kind="local", target_sha=m2.sha)]
    grid = build_grid([m2, f1, m1], refs, head_sha=m2.sha, head_branch="main", dirty=False)
    main_lane = grid.main_lane
    # Merge commit sits on main lane.
    assert grid.rows[0].lane == main_lane
    # f1 is the other parent, on a side lane.
    assert grid.rows[1].lane != main_lane
    # m1 is back on main lane.
    assert grid.rows[2].lane == main_lane
    assert grid.num_lanes >= 2


def test_two_simultaneous_branches() -> None:
    # main tip + feature tip + shared ancestor
    main_tip = _c("mt", ("anc",))
    feat_tip = _c("ft", ("anc",))
    anc = _c("anc", ())
    refs = [
        Ref(name="main", kind="local", target_sha=main_tip.sha),
        Ref(name="feature", kind="local", target_sha=feat_tip.sha),
    ]
    grid = build_grid(
        [main_tip, feat_tip, anc],
        refs,
        head_sha=main_tip.sha,
        head_branch="main",
        dirty=False,
    )
    assert grid.num_lanes >= 2
    # main tip sits on main_lane.
    assert grid.rows[0].lane == grid.main_lane
    # feature tip not on main_lane.
    assert grid.rows[1].lane != grid.main_lane
    # ancestor row picks one of the active lanes (main).
    assert grid.rows[2].lane == grid.main_lane


def test_main_centred_with_one_feature_each_side() -> None:
    # Three tips: main, featA, featB → main should be centred.
    a = _c("at", ("anc",))
    main_tip = _c("mt", ("anc",))
    b = _c("bt", ("anc",))
    anc = _c("anc", ())
    refs = [
        Ref(name="main", kind="local", target_sha=main_tip.sha),
        Ref(name="featA", kind="local", target_sha=a.sha),
        Ref(name="featB", kind="local", target_sha=b.sha),
    ]
    grid = build_grid(
        [main_tip, a, b, anc],
        refs,
        head_sha=main_tip.sha,
        head_branch="main",
        dirty=False,
    )
    # main lane is at the centre column of num_lanes.
    assert grid.main_lane == (grid.num_lanes - 1) // 2


def test_master_fallback_when_no_main() -> None:
    c = _c("c1")
    refs = [Ref(name="master", kind="local", target_sha=c.sha)]
    grid = build_grid([c], refs, head_sha=c.sha, head_branch="master", dirty=False)
    # The chosen main lane has a branch label of master in row 0.
    assert grid.rows[0].branch_label == "master"


def test_detached_head_layout_does_not_crash() -> None:
    c2 = _c("c2", ("c1",))
    c1 = _c("c1", ())
    refs = [Ref(name="main", kind="local", target_sha=c1.sha)]  # main NOT at HEAD
    grid = build_grid([c2, c1], refs, head_sha=c2.sha, head_branch=None, dirty=False)
    assert grid.rows[0].glyph_kind == "head"


def test_dirty_row_prepended_when_dirty() -> None:
    c = _c("c1")
    refs = [Ref(name="main", kind="local", target_sha=c.sha)]
    grid = build_grid([c], refs, head_sha=c.sha, head_branch="main", dirty=True)
    assert len(grid.rows) == 2
    assert grid.rows[0].glyph_kind == "dirty"
    assert grid.rows[0].commit is None
    assert grid.rows[1].glyph_kind == "head"


def test_tag_marks_glyph_kind() -> None:
    c2 = _c("c2", ("c1",))
    c1 = _c("c1", ())
    refs = [
        Ref(name="main", kind="local", target_sha=c2.sha),
        Ref(name="v1", kind="tag", target_sha=c1.sha),
    ]
    grid = build_grid([c2, c1], refs, head_sha=c2.sha, head_branch="main", dirty=False)
    assert grid.rows[1].glyph_kind == "tagged"


def test_sha_to_row_indexes_synthetic_dirty_correctly() -> None:
    c = _c("c1")
    refs = [Ref(name="main", kind="local", target_sha=c.sha)]
    grid = build_grid([c], refs, head_sha=c.sha, head_branch="main", dirty=True)
    # Synthetic row has no sha; real commit must be at index 1.
    assert grid.sha_to_row[c.sha] == 1
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/git_history/test_layout.py -v`
Expected: Most new tests fail (dirty row not implemented, branch label not consistent yet, etc.).

- [ ] **Step 3: Update `build_grid` to handle dirty row + branch labels properly**

Replace the body of `build_grid` in `jet/git_history/layout.py` with the following (everything between the function signature and `return GraphGrid(...)`):

```python
    if not commits:
        return GraphGrid(rows=(), num_lanes=1, main_lane=0, sha_to_row={}, lane_to_branch={})

    main_branch_name = _choose_main_branch(refs, head_branch)
    tag_targets = {r.target_sha for r in refs if r.kind == "tag"}
    refs_by_sha: dict[str, list[Ref]] = {}
    for r in refs:
        refs_by_sha.setdefault(r.target_sha, []).append(r)

    raw_rows, lane_to_branch = _assign_lanes(commits, refs, main_branch_name, head_sha)

    if dirty:
        # Prepend a synthetic row on the HEAD commit's lane.
        head_raw = next((r for r in raw_rows if r.commit and r.commit.sha == head_sha), raw_rows[0])
        raw_rows = [_RawRow(commit=None, lane=head_raw.lane), *raw_rows]

    # Compute centring.
    main_lane_raw = lane_to_branch_lane(lane_to_branch, main_branch_name)
    if main_lane_raw is None:
        main_lane_raw = raw_rows[0].lane

    used = sorted({row.lane for row in raw_rows})
    half = max(main_lane_raw - used[0], used[-1] - main_lane_raw)
    num_lanes = 2 * half + 1
    centre = half
    shift = centre - main_lane_raw

    rows: list[GraphRow] = []
    sha_to_row: dict[str, int] = {}
    shifted_lane_to_branch = {lane + shift: name for lane, name in lane_to_branch.items()}

    for idx, raw in enumerate(raw_rows):
        new_lane = raw.lane + shift
        commit = raw.commit
        if commit is None:
            kind: GlyphKind = "dirty"
        elif commit.sha == head_sha:
            kind = "head"
        elif commit.sha in tag_targets:
            kind = "tagged"
        else:
            kind = "normal"
        cells = _row_cells(num_lanes, new_lane, kind)
        commit_refs = tuple(refs_by_sha.get(commit.sha, [])) if commit else ()
        branch_label = _branch_label_for_row(idx, raw_rows, raw, shifted_lane_to_branch.get(new_lane))
        rows.append(
            GraphRow(
                commit=commit,
                lane=new_lane,
                glyph_kind=kind,
                cells=cells,
                refs=commit_refs,
                branch_label=branch_label,
            )
        )
        if commit is not None:
            sha_to_row[commit.sha] = idx

    return GraphGrid(
        rows=tuple(rows),
        num_lanes=num_lanes,
        main_lane=centre,
        sha_to_row=sha_to_row,
        lane_to_branch=shifted_lane_to_branch,
    )
```

(This replacement is mostly a clean restatement plus the dirty-row prepend. Keep the helper functions untouched.)

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/git_history/test_layout.py -v`
Expected: PASS for all layout tests.

If `test_master_fallback_when_no_main` fails because the branch label is missing, ensure `_assign_lanes` records `lane_to_branch[0] = main_branch` whenever `main_branch is not None and a matching local ref exists`. If `test_two_simultaneous_branches` fails because the feature tip ended up on the main lane, double-check that `_assign_lanes` does **not** include lane 0 in the alternating candidates set when allocating *non-main* new lanes (the candidates list starts at 0, so the first non-main allocation should still land on 0 only if 0 is free — guarantee that the main lane is seeded with the main sha or with HEAD before the loop, so it's never free for a side branch).

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/layout.py tests/git_history/test_layout.py
git commit -m "feat(git-history): branch/merge layout + dirty-row + main centring"
```

---

## Task 7: GitHistoryWidget skeleton (rendering only)

**Files:**
- Create: `jet/git_history/widget.py`
- Create: `tests/git_history/test_widget.py`

- [ ] **Step 1: Write failing widget test**

Write `tests/git_history/test_widget.py`:

```python
"""Widget tests using Textual pilot."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from jet.git_history.widget import GitHistoryWidget
from tests.git_history.fixtures.make_repo import commit, init_repo


class _Host(App):
    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self._workspace = workspace

    def compose(self) -> ComposeResult:
        yield GitHistoryWidget(self._workspace, id="git")


@pytest.mark.asyncio
async def test_widget_loads_grid_on_mount(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "first")
    commit(repo, "second")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None
        assert len(w.grid.rows) == 2
        assert w.cursor_sha is not None  # initial cursor on HEAD
```

- [ ] **Step 2: Run, expect ImportError**

Run: `pytest tests/git_history/test_widget.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Implement skeleton widget**

Write `jet/git_history/widget.py`:

```python
"""GitHistoryWidget — Textual ScrollView rendering a GraphGrid."""

from __future__ import annotations

from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.strip import Strip

from .layout import GraphGrid, build_grid
from .repo import Repo


class GitHistoryWidget(ScrollView):
    """Read-only commit-graph sidebar."""

    DEFAULT_CSS = """
    GitHistoryWidget {
        background: transparent;
        background-tint: transparent;
        color: #cdd6f4;
        border-right: solid white;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-size: 0 0;
        min-width: 12;
        max-width: 60;
        width: 18;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_repo", show=False),
    ]

    grid: reactive[GraphGrid | None] = reactive(None)
    cursor_sha: reactive[str | None] = reactive(None)

    class CommitFocused(Message):
        def __init__(self, sha: str | None, row: int) -> None:
            super().__init__()
            self.sha = sha
            self.row = row

    _STYLES = {
        "branch": Style(color="#cdd6f4"),
        "head": Style(color="#f9e2af", bold=True),
        "tagged": Style(color="#94e2d5"),
        "dirty": Style(color="#f9e2af"),
        "guide": Style(color="#2a2f3a"),
    }

    def __init__(self, workspace: Path, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.workspace = Path(workspace)
        self.repo = Repo(self.workspace)
        self._commits_loaded = 0

    def on_mount(self) -> None:
        self._load()

    # ------------------------------------------------------------------ data

    def _load(self) -> None:
        if not self.repo.is_git_repo():
            self.grid = None
            return
        commits = self.repo.log(limit=500)
        self._commits_loaded = len(commits)
        refs = self.repo.refs()
        head_sha, head_branch = self.repo.head() if commits else ("", None)
        dirty = self.repo.is_dirty() if commits else False
        self.grid = build_grid(commits, refs, head_sha, head_branch, dirty)
        if self.cursor_sha is None and head_sha:
            self.cursor_sha = head_sha
        # Resize virtual content for ScrollView.
        rows = len(self.grid.rows)
        cols = self.grid.num_lanes * 2 + 1
        self.virtual_size = self.virtual_size.__class__(cols, rows)  # textual.geometry.Size
        # Adjust visible width to fit lanes (clamped by CSS min/max).
        self.styles.width = max(12, min(60, self.grid.num_lanes * 2 + 4))

    def action_refresh_repo(self) -> None:
        self.repo.refresh()
        self._load()
        self.refresh()

    # ------------------------------------------------------------------ render

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        row_idx = y + scroll_y
        if self.grid is None or row_idx >= len(self.grid.rows):
            return Strip.blank(self.size.width)
        row = self.grid.rows[row_idx]
        segments: list[Segment] = []
        for lane_idx, cell in enumerate(row.cells):
            style = self._STYLES.get(cell.style, self._STYLES["branch"])
            if (
                self.cursor_sha is not None
                and row.commit is not None
                and row.commit.sha == self.cursor_sha
                and lane_idx == row.lane
            ):
                style = style + Style(reverse=True)
            segments.append(Segment(cell.glyph, style))
            if lane_idx < len(row.cells) - 1:
                segments.append(Segment(" ", self._STYLES["guide"]))
        strip = Strip(segments)
        strip = strip.crop(scroll_x, scroll_x + self.size.width)
        return strip
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/git_history/test_widget.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/widget.py tests/git_history/test_widget.py
git commit -m "feat(git-history): widget skeleton renders grid"
```

---

## Task 8: Widget keyboard navigation

**Files:**
- Modify: `jet/git_history/widget.py`
- Modify: `tests/git_history/test_widget.py`

- [ ] **Step 1: Write failing navigation tests**

Append to `tests/git_history/test_widget.py`:

```python
from tests.git_history.fixtures.make_repo import branch, checkout, merge


@pytest.mark.asyncio
async def test_cursor_up_moves_to_older_commit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "first")
    second = commit(repo, "second")
    third = commit(repo, "third")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None
        head_sha = w.grid.rows[0].commit.sha
        assert w.cursor_sha == head_sha
        w.action_cursor_down()  # toward older commits
        assert w.cursor_sha == w.grid.rows[1].commit.sha
        w.action_cursor_down()
        assert w.cursor_sha == w.grid.rows[2].commit.sha
        w.action_cursor_up()
        assert w.cursor_sha == w.grid.rows[1].commit.sha


@pytest.mark.asyncio
async def test_cursor_right_jumps_to_sibling_lane(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "base")
    branch(repo, "feature")
    feat = commit(repo, "feat")
    checkout(repo, "main")
    main_tip = commit(repo, "main2")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None and w.grid.num_lanes >= 2
        # Start at main tip (HEAD). After cursor_right we should land on the
        # feature tip OR another lane's earliest visible row — anything not on
        # the main lane.
        start_lane = next(r.lane for r in w.grid.rows if r.commit and r.commit.sha == w.cursor_sha)
        w.action_cursor_right()
        new_lane = next(r.lane for r in w.grid.rows if r.commit and r.commit.sha == w.cursor_sha)
        assert new_lane != start_lane


@pytest.mark.asyncio
async def test_commit_focused_message_posted_on_move(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "a")
    commit(repo, "b")
    received: list[GitHistoryWidget.CommitFocused] = []

    class _Capture(_Host):
        def on_git_history_widget_commit_focused(self, ev: GitHistoryWidget.CommitFocused) -> None:
            received.append(ev)

    app = _Capture(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        w.action_cursor_down()
        await pilot.pause()
        assert received, "expected a CommitFocused message"
```

- [ ] **Step 2: Run tests, expect AttributeError**

Run: `pytest tests/git_history/test_widget.py -v`
Expected: FAIL with `AttributeError: 'GitHistoryWidget' object has no attribute 'action_cursor_down'`.

- [ ] **Step 3: Add navigation actions**

Append to `GitHistoryWidget` in `jet/git_history/widget.py`:

```python
    # ------------------------------------------------------------------ nav

    def _current_row_idx(self) -> int | None:
        if self.grid is None or self.cursor_sha is None:
            return None
        return self.grid.sha_to_row.get(self.cursor_sha)

    def _row_for_sha(self, sha: str | None):
        if sha is None or self.grid is None:
            return None
        idx = self.grid.sha_to_row.get(sha)
        return None if idx is None else self.grid.rows[idx]

    def _commit_at_idx(self, idx: int) -> str | None:
        if self.grid is None or not (0 <= idx < len(self.grid.rows)):
            return None
        commit = self.grid.rows[idx].commit
        return commit.sha if commit is not None else None

    def action_cursor_down(self) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            for r in self.grid.rows:
                if r.commit is not None:
                    self.cursor_sha = r.commit.sha
                    self._post_focus(r)
                    return
            return
        current_lane = self.grid.rows[idx].lane
        for j in range(idx + 1, len(self.grid.rows)):
            row = self.grid.rows[j]
            if row.commit is not None and row.lane == current_lane:
                self._update_cursor(row)
                return
        for j in range(idx + 1, len(self.grid.rows)):
            row = self.grid.rows[j]
            if row.commit is not None:
                self._update_cursor(row)
                return

    def action_cursor_up(self) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            return
        current_lane = self.grid.rows[idx].lane
        for j in range(idx - 1, -1, -1):
            row = self.grid.rows[j]
            if row.commit is not None and row.lane == current_lane:
                self._update_cursor(row)
                return
        for j in range(idx - 1, -1, -1):
            row = self.grid.rows[j]
            if row.commit is not None:
                self._update_cursor(row)
                return

    def action_cursor_right(self) -> None:
        self._jump_lane(direction=+1)

    def action_cursor_left(self) -> None:
        self._jump_lane(direction=-1)

    def _jump_lane(self, *, direction: int) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            return
        current_lane = self.grid.rows[idx].lane
        # Find the nearest lane on the requested side that has any commit row.
        used_lanes = sorted({r.lane for r in self.grid.rows if r.commit is not None})
        if direction > 0:
            candidates = [l for l in used_lanes if l > current_lane]
        else:
            candidates = [l for l in reversed(used_lanes) if l < current_lane]
        for target_lane in candidates:
            # Pick that lane's earliest visible commit row (topmost).
            for row in self.grid.rows:
                if row.commit is not None and row.lane == target_lane:
                    self._update_cursor(row)
                    return

    def _update_cursor(self, row) -> None:
        if row.commit is None:
            return
        self.cursor_sha = row.commit.sha
        self.refresh()
        self._post_focus(row)
        self._ensure_visible(row)

    def _post_focus(self, row) -> None:
        idx = self.grid.sha_to_row.get(row.commit.sha) if (self.grid and row.commit) else None
        self.post_message(self.CommitFocused(sha=row.commit.sha if row.commit else None, row=idx or 0))

    def _ensure_visible(self, row) -> None:
        idx = self.grid.sha_to_row.get(row.commit.sha) if (self.grid and row.commit) else None
        if idx is None:
            return
        _, scroll_y = self.scroll_offset
        viewport = self.size.height
        if idx < scroll_y:
            self.scroll_to(y=idx, animate=False)
        elif idx >= scroll_y + viewport:
            self.scroll_to(y=max(0, idx - viewport + 1), animate=False)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/git_history/test_widget.py -v`
Expected: PASS (4 widget tests).

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/widget.py tests/git_history/test_widget.py
git commit -m "feat(git-history): widget keyboard nav up/down/left/right"
```

---

## Task 9: Infinite scroll on cursor_down

**Files:**
- Modify: `jet/git_history/widget.py`
- Modify: `tests/git_history/test_widget.py`

- [ ] **Step 1: Write failing test**

Append to `tests/git_history/test_widget.py`:

```python
@pytest.mark.asyncio
async def test_infinite_scroll_loads_more(tmp_path: Path, monkeypatch) -> None:
    repo = init_repo(tmp_path / "r")
    for i in range(8):
        commit(repo, f"c{i}")
    # Patch initial limit to 3 so we can exercise pagination.
    import jet.git_history.widget as widget_mod
    monkeypatch.setattr(widget_mod, "_INITIAL_LIMIT", 3)
    monkeypatch.setattr(widget_mod, "_PAGE_SIZE", 3)
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None and len(w.grid.rows) == 3
        # Step cursor down past the loaded slice.
        for _ in range(5):
            w.action_cursor_down()
        await pilot.pause()
        assert w.grid is not None
        assert len(w.grid.rows) > 3
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/git_history/test_widget.py::test_infinite_scroll_loads_more -v`
Expected: FAIL (`_INITIAL_LIMIT` not defined / no pagination triggered).

- [ ] **Step 3: Add pagination constants and trigger**

In `jet/git_history/widget.py`, add module-level constants near the top:

```python
_INITIAL_LIMIT = 500
_PAGE_SIZE = 500
_LOAD_AHEAD_ROWS = 5
```

Replace the body of `_load`:

```python
    def _load(self) -> None:
        if not self.repo.is_git_repo():
            self.grid = None
            return
        commits = self.repo.log(limit=_INITIAL_LIMIT)
        self._all_commits = commits
        self._commits_loaded = len(commits)
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        if not self._all_commits:
            self.grid = None
            return
        refs = self.repo.refs()
        head_sha, head_branch = self.repo.head()
        dirty = self.repo.is_dirty()
        self.grid = build_grid(self._all_commits, refs, head_sha, head_branch, dirty)
        if self.cursor_sha is None and self._all_commits:
            self.cursor_sha = self._all_commits[0].sha
        rows = len(self.grid.rows)
        cols = self.grid.num_lanes * 2 + 1
        self.virtual_size = self.virtual_size.__class__(cols, rows)
        self.styles.width = max(12, min(60, self.grid.num_lanes * 2 + 4))
```

Add `self._all_commits: list = []` in `__init__`.

Add the load-more trigger at the end of `action_cursor_down`:

```python
        # After moving, check whether we are close to the bottom and need more.
        self._maybe_load_more()
```

Implement `_maybe_load_more`:

```python
    def _maybe_load_more(self) -> None:
        if self.grid is None:
            return
        idx = self._current_row_idx()
        if idx is None:
            return
        if idx >= len(self.grid.rows) - _LOAD_AHEAD_ROWS:
            more = self.repo.log(limit=_PAGE_SIZE, skip=len(self._all_commits))
            if not more:
                return
            self._all_commits = self._all_commits + more
            old_cursor = self.cursor_sha
            self._rebuild_grid()
            self.cursor_sha = old_cursor
            self.refresh()
```

- [ ] **Step 4: Run all widget tests**

Run: `pytest tests/git_history/test_widget.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/widget.py tests/git_history/test_widget.py
git commit -m "feat(git-history): paginated history loading on scroll"
```

---

## Task 10: CommitDetailPopup widget

**Files:**
- Create: `jet/git_history/popup.py`
- Modify: `tests/git_history/test_widget.py`

- [ ] **Step 1: Write failing test**

Append to `tests/git_history/test_widget.py`:

```python
from jet.git_history.popup import CommitDetailPopup
from jet.git_history.repo import Commit, CommitStats


def test_popup_renders_stats_and_truncated_subject() -> None:
    c = Commit(
        sha="a" * 40,
        short="a" * 7,
        parents=(),
        author="x",
        timestamp=0,
        subject="this is a very long subject line that should be truncated nicely",
    )
    popup = CommitDetailPopup()
    popup.set_commit(c, stats=CommitStats(1, 12, 3, ()))
    rendered = popup.render()
    text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
    assert "+12 / -3" in text
    assert "this is a very long subject" in text
    # Truncated to 30 chars with ellipsis somewhere.
    assert "…" in text or "..." in text
```

- [ ] **Step 2: Run, expect ImportError**

Run: `pytest tests/git_history/test_widget.py::test_popup_renders_stats_and_truncated_subject -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement popup**

Write `jet/git_history/popup.py`:

```python
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/git_history/test_widget.py::test_popup_renders_stats_and_truncated_subject -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/popup.py tests/git_history/test_widget.py
git commit -m "feat(git-history): CommitDetailPopup widget"
```

---

## Task 11: BranchHeader sticky widget

**Files:**
- Create: `jet/git_history/branch_header.py`
- Modify: `jet/git_history/widget.py`
- Modify: `tests/git_history/test_widget.py`

- [ ] **Step 1: Write failing test**

Append to `tests/git_history/test_widget.py`:

```python
@pytest.mark.asyncio
async def test_branch_header_shows_main_label(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "init")
    commit(repo, "second")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        from jet.git_history.branch_header import BranchHeader
        header = app.query_one(BranchHeader)
        assert "main" in header.render_to_text()
```

- [ ] **Step 2: Run, expect ImportError**

Run: `pytest tests/git_history/test_widget.py::test_branch_header_shows_main_label -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement BranchHeader**

Write `jet/git_history/branch_header.py`:

```python
"""Sticky one-line header above the git history widget that shows lane labels."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from .layout import GraphGrid


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
        self.update(self.render_to_text())

    def render_to_text(self) -> str:
        grid = self.grid
        if grid is None or not grid.lane_to_branch:
            return ""
        lane_width = 2  # glyph + space
        out_chars: list[str] = [" "] * (grid.num_lanes * lane_width)
        for lane, name in grid.lane_to_branch.items():
            if not (0 <= lane < grid.num_lanes):
                continue
            truncated = name if len(name) <= lane_width else name[: lane_width - 1] + "…"
            start = lane * lane_width
            for i, ch in enumerate(truncated):
                if start + i < len(out_chars):
                    out_chars[start + i] = ch
        return "".join(out_chars)

    def render(self) -> Text:
        return Text(self.render_to_text())
```

- [ ] **Step 4: Mount header inside the widget**

In `jet/git_history/widget.py`, import the header:

```python
from .branch_header import BranchHeader
```

Override `compose` on `GitHistoryWidget`:

```python
    def compose(self):
        yield BranchHeader(id="git-branch-header")
```

In `_rebuild_grid`, after computing `self.grid`, push the grid to the header:

```python
        header = self.query_one(BranchHeader)
        header.grid = self.grid
```

Wrap the header access with `try/except NoMatches` if the widget is not yet composed (during the very first `_load`):

```python
        from textual.css.query import NoMatches
        try:
            header = self.query_one(BranchHeader)
        except NoMatches:
            header = None
        if header is not None:
            header.grid = self.grid
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/git_history/test_widget.py -v`
Expected: PASS (all widget tests).

- [ ] **Step 6: Commit**

```bash
git add jet/git_history/branch_header.py jet/git_history/widget.py tests/git_history/test_widget.py
git commit -m "feat(git-history): sticky BranchHeader with lane labels"
```

---

## Task 12: `commit_view.format_commit` + JetEditor read-only flag

**Files:**
- Create: `jet/git_history/commit_view.py`
- Modify: `jet/editor.py`
- Create: `tests/git_history/test_commit_view.py`

- [ ] **Step 1: Write failing tests for commit_view**

Write `tests/git_history/test_commit_view.py`:

```python
from __future__ import annotations

from pathlib import Path

from jet.git_history.commit_view import format_commit
from jet.git_history.repo import Repo
from tests.git_history.fixtures.make_repo import commit, init_repo, tag


def test_format_commit_includes_author_message_stats(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "first", content="a\n")
    commit(repo_path, "second\n\nbody line", content="a\nb\n")
    repo = Repo(repo_path)
    sha, _ = repo.head()
    text = format_commit(repo, sha)
    assert sha[:7] in text
    assert "second" in text
    assert "body line" in text
    assert "+1 / -0" in text
    assert "file.txt" in text


def test_format_commit_lists_tag_refs(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    tag(repo_path, "v0.1")
    repo = Repo(repo_path)
    sha, _ = repo.head()
    text = format_commit(repo, sha)
    assert "v0.1" in text
```

- [ ] **Step 2: Run tests, expect ImportError**

Run: `pytest tests/git_history/test_commit_view.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Implement commit_view**

Write `jet/git_history/commit_view.py`:

```python
"""Formatter that turns a commit into a plain-text read-only buffer body."""

from __future__ import annotations

import datetime

from .repo import Repo


def format_commit(repo: Repo, sha: str) -> str:
    commits = repo.log(limit=1, skip=0)  # not used; placeholder so signature is stable
    refs = repo.refs()
    matching_refs = [r for r in refs if r.target_sha == sha]
    stats = repo.stats(sha)
    full_msg = repo.full_message(sha)
    # Look up commit metadata via `git show` since `log` is bounded.
    meta = _commit_meta(repo, sha)

    lines: list[str] = []
    lines.append(f"commit {sha}                            (read-only)")
    lines.append("=" * 40)
    lines.append("")
    lines.append(f"Author:   {meta['author']}")
    lines.append(f"Date:     {meta['date_human']}  ({meta['date_relative']})")
    if matching_refs:
        refs_str = ", ".join(_ref_label(r) for r in matching_refs)
        lines.append(f"Refs:     {refs_str}")
    if meta["parents"]:
        lines.append(f"Parents:  {' '.join(meta['parents'])}")
    lines.append("")
    lines.append("-" * 40)
    lines.append(full_msg.strip())
    lines.append("-" * 40)
    lines.append("")
    lines.append(
        f"Files changed ({stats.files_changed}, "
        f"+{stats.insertions} / -{stats.deletions}):"
    )
    lines.append("")
    for path, ins, dels in stats.per_file:
        lines.append(f"  {path:<30} +{ins} / -{dels}")
    return "\n".join(lines) + "\n"


def _ref_label(ref) -> str:
    if ref.kind == "tag":
        return f"tag: {ref.name}"
    return ref.name


def _commit_meta(repo: Repo, sha: str) -> dict:
    out = repo._run(  # noqa: SLF001  (intentional access for module-internal use)
        "show",
        "-s",
        "--date=iso-local",
        "--format=%an <%ae>%n%ad%n%ar%n%P",
        sha,
    )
    lines = out.rstrip("\n").splitlines()
    author = lines[0] if lines else ""
    date_human = lines[1] if len(lines) > 1 else ""
    date_relative = lines[2] if len(lines) > 2 else ""
    parents = lines[3].split() if len(lines) > 3 and lines[3].strip() else []
    return {
        "author": author,
        "date_human": date_human,
        "date_relative": date_relative,
        "parents": [p[:7] for p in parents],
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/git_history/test_commit_view.py -v`
Expected: PASS.

- [ ] **Step 5: Write failing test for JetEditor read_only**

Append to `tests/test_app.py`:

```python
@pytest.mark.asyncio
async def test_editor_read_only_blocks_insertion(tmp_path: Path):
    from jet.app import JetApp
    f = tmp_path / "x.py"
    f.write_text("hello\n")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        ed = app._active_editor()
        assert ed is not None
        ed.read_only = True
        ed.focus()
        await pilot.press("a")
        await pilot.pause()
        assert ed.text == "hello\n"
```

- [ ] **Step 6: Run test**

Run: `pytest tests/test_app.py::test_editor_read_only_blocks_insertion -v`
Expected: PASS *or* FAIL depending on whether `read_only` already works. (Textual's `TextArea` exposes a `read_only` attribute, and `_on_key` in `JetEditor` already early-returns when `self.read_only` is true.) If it FAILS, complete step 7 below; otherwise note "already supported by base class" and skip step 7.

- [ ] **Step 7: Patch JetEditor `action_save` to honour read_only (if needed)**

Modify `jet/editor.py` — add at the top of `JetEditor`:

```python
    def __init__(
        self,
        text: str = "",
        *,
        path: Path | None = None,
        language: str | None = None,
        config: EditorConfig | None = None,
        read_only: bool = False,
        **kwargs,
    ) -> None:
        ...  # existing body
        self.read_only = read_only  # set after super().__init__ which expects it
```

(Place `self.read_only = read_only` after the `super().__init__(...)` call.)

Then ensure `JetApp.action_save` notifies and returns when the active editor is read-only — patch the start of `action_save` in `jet/app.py`:

```python
        if ed.read_only:
            self.notify("Buffer is read-only")
            return
```

- [ ] **Step 8: Run all editor tests**

Run: `pytest tests/test_app.py tests/git_history/test_commit_view.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add jet/git_history/commit_view.py jet/editor.py jet/app.py tests/test_app.py tests/git_history/test_commit_view.py
git commit -m "feat(git-history): format_commit + JetEditor read_only flag"
```

---

## Task 13: App integration — mount sidebar, cycle, route nav, open buffer, sync popup

**Files:**
- Modify: `jet/app.py`
- Modify: `jet/styles.tcss`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing integration test for cycling**

Append to `tests/test_app.py`:

```python
@pytest.mark.asyncio
async def test_sidebar_cycle_includes_git_in_repo(tmp_path: Path):
    from jet.app import JetApp
    from tests.git_history.fixtures.make_repo import commit, init_repo
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    f = repo_path / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        # tree → git
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is False
        assert app.query_one("#sidebar-git").display is True
        assert app.query_one("#sidebar-settings").display is False
        # git → settings
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-git").display is False
        assert app.query_one("#sidebar-settings").display is True
        # settings → tree
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is True


@pytest.mark.asyncio
async def test_sidebar_cycle_skips_git_outside_repo(tmp_path: Path):
    """When workspace is not a git repo the git sidebar is removed from cycle."""
    from jet.app import JetApp
    from textual.css.query import NoMatches
    f = tmp_path / "x.py"
    f.write_text("a=1\n")
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        # Either #sidebar-git doesn't exist or is permanently hidden.
        try:
            git_w = app.query_one("#sidebar-git")
            assert git_w.display is False
        except NoMatches:
            pass
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-settings").display is True


@pytest.mark.asyncio
async def test_shift_tab_opens_commit_buffer(tmp_path: Path):
    from jet.app import JetApp
    from textual.widgets import TabbedContent, TabPane
    from tests.git_history.fixtures.make_repo import commit, init_repo
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init", content="a\n")
    second = commit(repo_path, "second", content="a\nb\n")
    f = repo_path / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        # Cycle to git sidebar, then focus its widget.
        await pilot.press("ctrl+b")
        from jet.git_history.widget import GitHistoryWidget
        git_w = app.query_one(GitHistoryWidget)
        git_w.focus()
        await pilot.pause()
        await pilot.press("shift+tab")
        await pilot.pause()
        tabs = app.query_one(TabbedContent)
        panes = list(tabs.query(TabPane))
        # A new tab with a `<commit:` title should now exist.
        titles = [str(tabs.get_tab(p.id).label) for p in panes if p.id]
        assert any("commit:" in t for t in titles)
```

- [ ] **Step 2: Run, expect failures**

Run: `pytest tests/test_app.py -v`
Expected: FAIL (sidebar-git not in compose, cycle doesn't include git, etc.).

- [ ] **Step 3: Update `SIDEBAR_ORDER` and `compose`**

In `jet/app.py`:

Replace `SIDEBAR_ORDER` and `SIDEBAR_SELECTORS`:

```python
SIDEBAR_ORDER: tuple[str, ...] = ("tree", "git", "settings")
SIDEBAR_SELECTORS: dict[str, str] = {
    "tree": "#sidebar-tree",
    "git": "#sidebar-git",
    "settings": "#sidebar-settings",
}
```

Add the new import at the top of the file:

```python
from .git_history.widget import GitHistoryWidget
from .git_history.popup import CommitDetailPopup
from .git_history.commit_view import format_commit
```

Update `compose` to mount the widgets:

```python
    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            yield JetTree(str(self.workspace), id="sidebar-tree")
            yield GitHistoryWidget(self.workspace, id="sidebar-git")
            yield SettingsPanel(self._editor_config, id="sidebar-settings")
            yield TabbedContent(id="tabs")
        yield _StatusBar(id="statusbar")
        yield _MatchCounter(id="match-counter")
        yield CommitDetailPopup(id="commit-popup")
```

In `__init__`, add:

```python
        self._sidebar_order: tuple[str, ...] = SIDEBAR_ORDER
```

In `on_mount`, after the existing setup, add:

```python
        git_w = self.query_one("#sidebar-git", GitHistoryWidget)
        if not git_w.repo.is_git_repo():
            await git_w.remove()
            self._sidebar_order = tuple(s for s in SIDEBAR_ORDER if s != "git")
        else:
            git_w.display = False
```

Update `action_cycle_sidebars` and `action_toggle_sidebar` to use `self._sidebar_order` instead of the class constant `SIDEBAR_ORDER`. Concretely:

```python
    def action_cycle_sidebars(self) -> None:
        cur = self._active_sidebar
        if cur not in self._sidebar_order:
            cur = self._sidebar_order[0]
            self._active_sidebar = cur
        cur_w = self.query_one(SIDEBAR_SELECTORS[cur])
        if not cur_w.display:
            cur_w.display = True
            self._refocus_editor()
            return
        cur_w.display = False
        nxt = self._sidebar_order[(self._sidebar_order.index(cur) + 1) % len(self._sidebar_order)]
        self.query_one(SIDEBAR_SELECTORS[nxt]).display = True
        if nxt == "git":
            self.query_one("#sidebar-git", GitHistoryWidget).focus()
        else:
            self._refocus_editor()
        self._active_sidebar = nxt
```

- [ ] **Step 4: Add `_visible_git_sidebar` helper + route Shift+arrow + Shift+Tab**

Add to `JetApp`:

```python
    def _visible_git_sidebar(self) -> GitHistoryWidget | None:
        try:
            w = self.query_one("#sidebar-git", GitHistoryWidget)
        except Exception:
            return None
        return w if w.display else None
```

Patch each of the four `action_sidebar_*` methods to short-circuit when git is visible:

```python
    def action_sidebar_up(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_up()
            return
        # ...existing tree / settings branches unchanged

    def action_sidebar_down(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_down()
            return
        # ...existing

    async def action_sidebar_open(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_right()
            return
        # ...existing

    def action_sidebar_close(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_left()
            return
        # ...existing
```

Patch `action_move_toggle`:

```python
    def action_move_toggle(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus and git.cursor_sha is not None:
            self._open_commit_buffer(git.cursor_sha)
            return
        # ...existing tree move logic unchanged
```

Implement `_open_commit_buffer`:

```python
    @work
    async def _open_commit_buffer(self, sha: str) -> None:
        git = self._visible_git_sidebar()
        if git is None:
            return
        short = sha[:7]
        virtual_path = Path(f"<commit:{short}>")
        tabs = self.query_one(TabbedContent)
        for pane in tabs.query(TabPane):
            try:
                ed = pane.query_one(JetEditor)
            except Exception:
                continue
            if ed.path == virtual_path:
                tabs.active = pane.id or ""
                ed.focus()
                return
        text = format_commit(git.repo, sha)
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        editor = JetEditor(
            text=text,
            path=virtual_path,
            config=self._editor_config,
            read_only=True,
            id=f"ed-{self._tab_counter}",
        )
        await tabs.add_pane(TabPane(f"<commit:{short}>", editor, id=tab_id))
        tabs.active = tab_id
        editor.focus()
```

- [ ] **Step 5: Run integration tests**

Run: `pytest tests/test_app.py -v -k "sidebar_cycle or shift_tab"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add jet/app.py tests/test_app.py
git commit -m "feat(git-history): wire git sidebar into app cycle + Shift+Tab buffer"
```

---

## Task 14: Popup positioning + focus sync

**Files:**
- Modify: `jet/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_app.py`:

```python
@pytest.mark.asyncio
async def test_popup_visible_only_while_git_focused(tmp_path: Path):
    from jet.app import JetApp
    from jet.git_history.widget import GitHistoryWidget
    from jet.git_history.popup import CommitDetailPopup
    from tests.git_history.fixtures.make_repo import commit, init_repo
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "init")
    commit(repo_path, "second")
    f = repo_path / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")  # show git sidebar
        git_w = app.query_one(GitHistoryWidget)
        git_w.focus()
        await pilot.pause()
        popup = app.query_one(CommitDetailPopup)
        assert popup.display is True
        # Focus the editor — popup should hide.
        ed = app._active_editor()
        assert ed is not None
        ed.focus()
        await pilot.pause()
        assert popup.display is False
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_app.py::test_popup_visible_only_while_git_focused -v`
Expected: FAIL — popup never displayed or not hidden.

- [ ] **Step 3: Implement popup sync + message handler**

Add to `JetApp` in `jet/app.py`:

```python
    def on_descendant_focus(self, event) -> None:  # type: ignore[override]
        self._sync_git_popup()

    def on_descendant_blur(self, event) -> None:  # type: ignore[override]
        self._sync_git_popup()

    @on(GitHistoryWidget.CommitFocused)
    def _on_commit_focused(self, event: GitHistoryWidget.CommitFocused) -> None:
        git = self._visible_git_sidebar()
        if git is None or event.sha is None:
            return
        popup = self.query_one("#commit-popup", CommitDetailPopup)
        # Fill content (stats may be lazy).
        commit = next(
            (c for c in git._all_commits if c.sha == event.sha),  # noqa: SLF001
            None,
        )
        stats = git.repo.stats(event.sha) if commit is not None else None
        popup.set_commit(commit, stats)
        self._position_popup(event.row)
        self._sync_git_popup()

    def _position_popup(self, row: int) -> None:
        popup = self.query_one("#commit-popup", CommitDetailPopup)
        try:
            git = self.query_one("#sidebar-git", GitHistoryWidget)
        except Exception:
            return
        region = git.region
        scroll_y = git.scroll_offset.y
        header_height = 1
        x = region.right + 1
        y = region.y + header_height + (row - scroll_y)
        screen_h = self.size.height
        if y + 4 > screen_h:
            y = max(0, y - 4)
        popup.styles.offset = (x, y)

    def _sync_git_popup(self) -> None:
        try:
            popup = self.query_one("#commit-popup", CommitDetailPopup)
            git = self.query_one("#sidebar-git", GitHistoryWidget)
        except Exception:
            return
        visible = bool(
            git.display
            and git.has_focus
            and git.cursor_sha is not None
            and git.grid is not None
        )
        popup.display = visible
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_app.py::test_popup_visible_only_while_git_focused -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jet/app.py tests/test_app.py
git commit -m "feat(git-history): floating popup with focus-bound visibility"
```

---

## Task 15: Mouse click selects commit (M7)

**Files:**
- Modify: `jet/git_history/widget.py`
- Modify: `tests/git_history/test_widget.py`

- [ ] **Step 1: Write failing test**

Append to `tests/git_history/test_widget.py`:

```python
@pytest.mark.asyncio
async def test_mouse_click_selects_commit(tmp_path: Path) -> None:
    from textual import events
    repo = init_repo(tmp_path / "r")
    commit(repo, "first")
    commit(repo, "second")
    commit(repo, "third")
    app = _Host(repo)
    async with app.run_test() as pilot:
        await pilot.pause()
        w = app.query_one(GitHistoryWidget)
        assert w.grid is not None
        target_sha = w.grid.rows[2].commit.sha  # oldest commit
        # Simulate a click at y=2 (third row), x within the lane.
        click = events.Click(
            chain=1,
            x=0,
            y=2,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            screen_x=0,
            screen_y=2,
            widget=w,
        )
        await w._on_click(click)
        await pilot.pause()
        assert w.cursor_sha == target_sha
```

Note: the exact `events.Click` constructor signature has varied across Textual versions; if any kwarg is wrong, run `python -c "from textual.events import Click; help(Click)"` and adjust the call. Acceptable alternative: invoke `w.on_click(...)` and pass a simple `types.SimpleNamespace(x=0, y=2)` stand-in.

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/git_history/test_widget.py::test_mouse_click_selects_commit -v`
Expected: FAIL — cursor unchanged.

- [ ] **Step 3: Implement `on_click`**

Append to `GitHistoryWidget` in `jet/git_history/widget.py`:

```python
    def on_click(self, event) -> None:
        if self.grid is None:
            return
        scroll_x, scroll_y = self.scroll_offset
        row_idx = event.y + scroll_y
        if not (0 <= row_idx < len(self.grid.rows)):
            return
        row = self.grid.rows[row_idx]
        if row.commit is None:
            return
        self._update_cursor(row)
```

Also expose `_on_click` if tests rely on that name:

```python
    async def _on_click(self, event) -> None:  # type: ignore[override]
        self.on_click(event)
        await super()._on_click(event) if hasattr(super(), "_on_click") else None
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/git_history/test_widget.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jet/git_history/widget.py tests/git_history/test_widget.py
git commit -m "feat(git-history): click to select commit"
```

---

## Task 16: CSS polish + manual smoke

**Files:**
- Modify: `jet/styles.tcss`

- [ ] **Step 1: Add scoped selectors to styles.tcss**

Append to `jet/styles.tcss`:

```css
/* Git history sidebar */
#sidebar-git {
    background: transparent;
    background-tint: transparent;
}

#commit-popup {
    layer: overlay;
}

BranchHeader {
    color: #7f8a99;
}
```

If Textual complains that `layer: overlay` is undeclared, add `layers: overlay;` to the `Screen` rule near the top of the file.

- [ ] **Step 2: Run all tests**

Run: `pytest -v`
Expected: PASS for all tests in `tests/git_history/` and `tests/test_app.py`.

- [ ] **Step 3: Manual smoke test**

Run the editor against the `jet` repo itself:

```bash
python -m jet .
```

Verify:
- `Ctrl+B` cycles `tree → git → settings`.
- Up/Down/Left/Right with `Shift` navigates inside the git sidebar.
- Popup appears next to the cursor; disappears when focus returns to the editor.
- `Shift+Tab` opens a `<commit:xxxxxxx>` tab containing the formatted commit detail; saving it produces "Buffer is read-only".
- `r` refreshes the sidebar.

- [ ] **Step 4: Commit**

```bash
git add jet/styles.tcss
git commit -m "style(git-history): scoped CSS polish for sidebar/popup/header"
```

---

## Task 17: Integration test — end-to-end nav across a real fixture repo

**Files:**
- Create: `tests/git_history/test_integration.py`

- [ ] **Step 1: Write the integration test**

Write `tests/git_history/test_integration.py`:

```python
"""End-to-end: build a multi-branch fixture repo, drive the app, assert state."""

from __future__ import annotations

from pathlib import Path

import pytest

from jet.app import JetApp
from jet.git_history.widget import GitHistoryWidget
from jet.git_history.popup import CommitDetailPopup
from tests.git_history.fixtures.make_repo import (
    branch,
    checkout,
    commit,
    init_repo,
    merge,
    tag,
)


@pytest.mark.asyncio
async def test_navigate_branched_history(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "r")
    commit(repo, "main-1")
    branch(repo, "feature")
    commit(repo, "feat-1")
    commit(repo, "feat-2")
    checkout(repo, "main")
    commit(repo, "main-2")
    merge(repo, "feature")
    tag(repo, "v1.0")
    f = repo / "file.txt"
    app = JetApp(paths=[f])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+b")  # show git sidebar
        git_w = app.query_one(GitHistoryWidget)
        git_w.focus()
        await pilot.pause()
        assert git_w.grid is not None
        assert git_w.grid.num_lanes >= 2
        # Walk down a few commits.
        head_sha = git_w.cursor_sha
        await pilot.press("shift+down")
        await pilot.press("shift+down")
        await pilot.pause()
        assert git_w.cursor_sha != head_sha
        # Pop the commit buffer with Shift+Tab.
        await pilot.press("shift+tab")
        await pilot.pause()
        from textual.widgets import TabbedContent, TabPane
        tabs = app.query_one(TabbedContent)
        titles = [str(tabs.get_tab(p.id).label) for p in tabs.query(TabPane) if p.id]
        assert any("commit:" in t for t in titles)
        # Popup is visible while git widget has focus.
        git_w.focus()
        await pilot.pause()
        popup = app.query_one(CommitDetailPopup)
        assert popup.display is True
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/git_history/test_integration.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/git_history/test_integration.py
git commit -m "test(git-history): end-to-end integration test"
```

---

## Task 18: Wrap-up — full test pass + final commit

- [ ] **Step 1: Run the entire suite**

Run: `pytest -v`
Expected: PASS for every test, including pre-existing ones.

If any pre-existing test regressed (most likely
`test_sidebar_cycle_tree_settings` due to the inserted `git` slot), update it:

```python
@pytest.mark.asyncio
async def test_sidebar_cycle_tree_settings(tmp_path):
    # Workspace is NOT a repo, so the git slot is skipped — cycle stays
    # tree → settings → tree.
    f = tmp_path / "x.py"
    f.write_text("a=1\n")
    app = JetApp([f])
    async with app.run_test() as pilot:
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is False
        assert app.query_one("#sidebar-settings").display is True
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-tree").display is True
        assert app.query_one("#sidebar-settings").display is False
```

- [ ] **Step 2: Final commit**

If step 1 required changes:

```bash
git add tests/test_app.py
git commit -m "test: adjust sidebar-cycle test for new git slot"
```

Otherwise, no additional commit is needed.

---

## Out-of-scope reminders

These were explicitly excluded in the spec (§ 11) and have **no task** in this plan:

- No diff modal (`Enter` is a no-op on the git sidebar).
- No checkout, cherry-pick, revert, or any other write operation.
- No filtering/search inside the graph.
- No persistent disk cache.
- No remote fetch/pull. Refresh is local-only.
