# Git History Sidebar — Design

**Date:** 2026-05-23
**Status:** Approved — ready for implementation plan
**Scope:** New `git` sidebar for `jet` showing a minimalist, vertical, top-growing
visualization of the repository's commit graph, with a focus-bound mini popup,
sticky branch labels, and a Shift+Tab read-only "commit detail" buffer.

---

## 1. Goal

Add a third sidebar to `JetApp` (in addition to the existing `tree` and
`settings` sidebars) that displays the project's git history as an interactive
graph. The sidebar is read-only — it never mutates the repository. Visual style
matches the rest of the editor: transparent background, no chrome, glyphs over
empty space.

The graph grows upward as new commits arrive: the most recent commit is at the
top of the sidebar; older commits are below; the bottom of the visible region
is the oldest loaded commit. New branches push siblings to the side; `main`
(or its fallback) is always rendered in the centre column.

---

## 2. User-facing behaviour

### 2.1 Activation
- `Ctrl+B` cycles sidebars in the order `tree → git → settings → tree …`
  (skipping `git` entirely when the workspace is not a git repo).
- `Ctrl+L` toggles the active sidebar (existing behaviour, unchanged).
- The sidebar is hidden by default and only mounted when the workspace is a
  git repository (`git rev-parse --git-dir` succeeds inside the workspace).

### 2.2 Navigation (when the git sidebar has focus)
- `Shift+Up` / `Shift+Down`: move the cursor to the previous/next commit on
  the same lane. If no further commit exists on the same lane in the requested
  direction, jump to the nearest commit in any visible lane.
- `Shift+Left` / `Shift+Right`: jump to the most recent commit currently
  visible in the lane immediately to the left/right of the cursor lane.
- `Shift+Tab`: open the commit detail buffer (§ 5.3).
- `Enter`: no-op (intentional — keeps the surface minimal).
- `r`: refresh the repository state.
- Mouse click on a commit glyph: move the cursor to that commit.
- Mouse scroll: scroll the sidebar.

### 2.3 Visual elements
- **Graph**: vertical lanes (`│`), commit dots on lanes (`●`/`★`/`◆`),
  branch/merge connectors (`╱`, `╲`, `┐`, `┘`, `├`, `┤`, etc.).
- **HEAD**: glyph `★` (instead of `●`).
- **Tagged commit**: glyph `◆` (when not HEAD).
- **Cursor**: inverts the colour of the underlying glyph; never replaces it.
- **Uncommitted changes marker**: a synthetic row above HEAD with glyph `✱`
  in yellow. Cursor skips it during ordinary up/down navigation, but the user
  can land on it via mouse click or by pressing Shift+Up from HEAD.
- **Sticky branch labels**: top row of the sidebar viewport shows the branch
  name above each lane that has a known branch tip. Labels are truncated to
  `lane_width - 1` characters with an ellipsis. Anonymous lanes show blank.

### 2.4 Mini popup (focus-bound)
A small floating box appears next to the cursor commit while the git sidebar
has focus. It contains only two lines:

```
┌────────────────────────────┐
│ +12 / -3                   │
│ fix: parse error in cli…   │
└────────────────────────────┘
```

- Line 1: insertions/deletions for the selected commit (lazy-fetched, shows
  `…` while loading).
- Line 2: commit subject truncated to 30 characters with an ellipsis.
- Fixed width 32, fixed height 4 (border + 2 content lines), rounded border.
- Position: immediately to the right of the sidebar, vertically aligned with
  the cursor row; flips upward if it would overflow the screen.
- Visibility: **only** when the git sidebar has focus, is displayed, and has
  a cursor. Focus moves to the editor or any other widget → popup hides.

### 2.5 Commit detail buffer (`Shift+Tab`)
Pressing `Shift+Tab` while the cursor is on a commit opens a new read-only
tab whose contents are formatted plain text describing the commit. Format:

```
commit a1b2c3d4e5f6...                            (read-only)
========================================

Author:   Jorge Martínez <jorge@example.com>
Date:     2026-05-20 14:32:11 +0100  (3 days ago)
Refs:     main, origin/main, tag: v1.2.0
Parents:  e7f8a9b (linear)

────────────────────────────────────────
fix: parse error in cli flag handling

The --output flag was being parsed before the
positional argument, causing argparse to fail
silently on empty inputs.
────────────────────────────────────────

Files changed (3, +12 / -3):

  jet/cli.py             +8 / -2
  jet/runner.py          +3 / -1
  tests/test_cli.py      +1 / -0
```

The tab title is `<commit:a1b2c>` (using the short hash). The buffer is opened
via the existing `TabbedContent` and uses `JetEditor` with a new
`read_only=True` flag (writes blocked, `action_save` no-ops with a
notification). The user closes it via `Ctrl+W` like any other tab.

When the cursor is on the synthetic uncommitted-changes row, `Shift+Tab`
opens a buffer that shows `git status` + `git diff --stat` instead.

---

## 3. Architecture

Three layers, no cross-coupling:

```
jet/git_history/
  __init__.py
  repo.py              # subprocess git → Commit, Ref, CommitStats dataclasses
  layout.py            # pure: commits + refs → GraphGrid
  widget.py            # GitHistoryWidget (Textual ScrollView)
  popup.py             # CommitDetailPopup (Textual Static, screen-level)
  branch_header.py     # BranchHeader (Static, sticky lane labels)
  commit_view.py       # format_commit(repo, sha) -> str for detail buffer
```

- `repo.py` is the only module that runs subprocesses. Testable by patching
  `subprocess.run` or by exercising against a real fixture repo.
- `layout.py` is a pure function on dataclasses. No I/O, no Textual imports.
  This is the algorithmic heart and the primary unit-test surface.
- `widget.py` consumes a `GraphGrid` and renders. No git knowledge, no
  layout logic.
- `popup.py` and `branch_header.py` are dumb display widgets.
- `commit_view.py` produces a plain string from a `Repo` and a sha.

Public API between layers:

```
repo.py     → Repo, Commit, Ref, CommitStats
layout.py   → build_grid(commits, refs, head_sha, head_branch, dirty)
            → GraphGrid (GraphRow, GraphCell)
widget.py   → GitHistoryWidget, GitHistoryWidget.CommitFocused (Message)
popup.py    → CommitDetailPopup
commit_view → format_commit(repo, sha) -> str
```

---

## 4. Data layer (`repo.py`)

### 4.1 Dataclasses

```python
@dataclass(frozen=True)
class Commit:
    sha: str             # 40-char hash
    short: str           # 7-char hash
    parents: tuple[str, ...]
    author: str          # "Name <email>"
    timestamp: int       # unix seconds
    subject: str         # first line of message

@dataclass(frozen=True)
class Ref:
    name: str            # "main", "origin/main", "v1.2.0"
    kind: Literal["local", "remote", "tag"]
    target_sha: str

@dataclass(frozen=True)
class CommitStats:
    files_changed: int
    insertions: int
    deletions: int
    per_file: tuple[tuple[str, int, int], ...]   # (path, +, -)
```

### 4.2 Repo class

```python
class Repo:
    def __init__(self, workspace: Path) -> None: ...
    def is_git_repo(self) -> bool
    def head(self) -> tuple[str, str | None]          # (sha, branch|None for detached)
    def is_dirty(self) -> bool
    def log(self, limit: int = 500, skip: int = 0) -> list[Commit]
    def refs(self) -> list[Ref]
    def stats(self, sha: str) -> CommitStats          # cached
    def full_message(self, sha: str) -> str           # cached, for commit_view
    def status_diff_stat(self) -> str                 # for the dirty buffer
```

### 4.3 Subprocess invocations

All commands run with `cwd=self.workspace`, `text=True`,
`errors="replace"`, `timeout=5.0`.

- `git rev-parse --git-dir` (used by `is_git_repo`).
- `git log --all --pretty=format:'%H%x1f%h%x1f%P%x1f%an <%ae>%x1f%at%x1f%s' -n <limit> --skip=<skip>`.
  Records separated by `\n`, fields by `\x1f` (ASCII unit separator). Parents
  is a space-separated list inside its field.
- `git for-each-ref --format='%(refname)%x1f%(objectname)' refs/heads refs/remotes refs/tags`.
  Maps `refname` prefix to `kind`. Strips `refs/heads/`, `refs/remotes/`,
  `refs/tags/` to produce the display `name`.
- `git status --porcelain --untracked-files=no` piped through Python (read
  only the first line; non-empty → dirty).
- `git diff-tree --numstat --no-commit-id -r <sha>` for stats. Each line is
  `<+>\t<->\t<path>`. Binary files report `-\t-\t<path>` → treat as 0/0.
- `git show -s --format='%B' <sha>` for the full message.
- `git status` + `git diff --stat` concatenated for the dirty buffer.

### 4.4 Caching

- `stats` → `functools.lru_cache(maxsize=1024)` on a private method.
- `full_message` → same, `maxsize=128`.
- Cache is wiped on `refresh()` (called from the widget when the user presses
  `r` or when the sidebar becomes visible).

---

## 5. Layout layer (`layout.py`)

### 5.1 Dataclasses

```python
GlyphKind = Literal["normal", "head", "tagged", "dirty"]

@dataclass(frozen=True)
class GraphCell:
    glyph: str
    style: str           # "guide" | "branch" | "current_branch" | "head" | ...

@dataclass(frozen=True)
class GraphRow:
    commit: Commit | None        # None for synthetic dirty row
    lane: int                    # column of the dot in `cells`
    glyph_kind: GlyphKind
    cells: tuple[GraphCell, ...] # full row, width == num_lanes * 2 - 1
    refs: tuple[Ref, ...]
    branch_label: str | None     # branch name if this row is a tip on its lane

@dataclass(frozen=True)
class GraphGrid:
    rows: tuple[GraphRow, ...]   # row 0 = newest (rendered at top)
    num_lanes: int
    main_lane: int               # index of main lane
    sha_to_row: dict[str, int]
    lane_to_branch: dict[int, str]
```

### 5.2 Algorithm

`build_grid(commits, refs, head_sha, head_branch, dirty) -> GraphGrid`.

`commits` is already ordered newest-first (matches `git log` output).

1. **Main detection.** Pick the principal branch by walking this list in
   order and choosing the first `Ref` of kind `local` whose name matches:
   `main`, `master`, `trunk`. If none match, use `head_branch` if not `None`.
   If still none (orphan/detached), use the lane of the HEAD commit.
2. **Lane state.** Maintain `active_lanes: dict[int, str]` mapping lane index
   → the SHA each lane is *expecting next* (i.e. the next commit that should
   appear on that lane).
3. **First-pass lane assignment.** Iterate `commits` in order. For each
   commit:
   - If its sha appears as a value in `active_lanes`, pick the lane(s) that
     match. The first matching lane (preferring `main_lane` if multiple)
     becomes this commit's lane; any other lanes that expected this sha are
     *closed* with a diagonal in the next row drawing pass.
   - Otherwise this commit is a *new tip*: allocate a fresh lane. The lane
     index is chosen by an alternating-counter that starts at 0 (centre)
     and goes `+1, -1, +2, -2, +3, -3 …`, picking the first slot that is
     not currently active. The very first new tip lane (`main`) is forced
     to the `main_lane` value chosen in step 1.
   - Set `active_lanes` for this commit's parents:
     - First parent: occupies this commit's lane.
     - Additional parents (merge): allocated to fresh lanes via the same
       alternating-counter rule. If a parent sha is already present as a
       value in `active_lanes`, reuse that lane (the merge "absorbs" the
       sibling lane) and record a diagonal join.
4. **Lane recentring.** After all rows are assigned, compute
   `min_lane = min(used_lanes)` and `max_lane = max(used_lanes)`. To keep
   `main` centred, choose `num_lanes = 2 * max(main - min_lane,
   max_lane - main) + 1`, then shift every lane index by the offset that
   maps `main` to `(num_lanes - 1) / 2`.
5. **Cell rendering.** Build `cells` per row from the lane assignment plus
   the diagonals recorded in step 3. Each lane occupies two character cells
   (glyph + space) except the last lane, which is single-width. Width of a
   row: `num_lanes * 2 - 1`.
6. **Glyph kind.** For the commit on row r:
   - `dirty` if synthetic row (only for the topmost row, conditional on
     `dirty=True`).
   - `head` if `commit.sha == head_sha`.
   - `tagged` if any ref of kind `tag` points to this sha.
   - `normal` otherwise.
7. **Refs & branch label.** Attach all refs pointing to this commit. If the
   commit is the *first row of its lane* (i.e. the tip of that lane in the
   loaded slice) and at least one local-branch ref points to it, set
   `branch_label = local_ref.name`. Otherwise `None`.
8. **Lane cap.** If `num_lanes > 11` (5 left + main + 5 right), collapse the
   outermost lanes on each side into a single `…` indicator lane.

### 5.3 Synthetic dirty row

When `dirty=True`, prepend a `GraphRow` with `commit=None`,
`lane=main_lane`, `glyph_kind="dirty"`. The row's cells render `✱` on the
HEAD lane and `│` on every other active lane.

### 5.4 Edge cases

- **Empty repo** (no commits): `build_grid` returns
  `GraphGrid(rows=(), num_lanes=1, main_lane=0, ...)`. Widget shows `no
  commits yet` centred.
- **Detached HEAD** (`head_branch is None`): no special branch label for the
  HEAD lane; main_lane resolves via the `main / master / trunk` fallback or
  defaults to the HEAD's lane.
- **Orphan commits** (commits whose parents are not in the loaded slice):
  their lane terminates at the bottom with `┴`.
- **Octopus merge** (3+ parents): all parents allocated lanes, all diagonals
  drawn. No special styling.

---

## 6. Widget layer (`widget.py`)

### 6.1 GitHistoryWidget

```python
class GitHistoryWidget(ScrollView):
    BINDINGS = [
        Binding("r", "refresh_repo", show=False),
    ]

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
    }
    """

    class CommitFocused(Message):
        def __init__(self, sha: str | None, row: int) -> None: ...

    grid: reactive[GraphGrid | None] = reactive(None)
    cursor_sha: reactive[str | None] = reactive(None)

    def __init__(self, workspace: Path, *, id: str | None = None): ...
    def on_mount(self) -> None: ...
    def render_line(self, y: int) -> Strip: ...
    def action_cursor_up(self) -> None: ...
    def action_cursor_down(self) -> None: ...
    def action_cursor_left(self) -> None: ...
    def action_cursor_right(self) -> None: ...
    def action_refresh_repo(self) -> None: ...
    def on_click(self, event: events.Click) -> None: ...
```

### 6.2 Rendering

`render_line` is the only render path. For each visible viewport row:

1. Translate viewport y to grid row index, taking `scroll_y` into account
   and reserving row 0 of the viewport for the sticky `BranchHeader`.
2. Map `GraphRow.cells` to `rich.segment.Segment` objects, applying styles
   from a small theme dictionary. The cursor sha matches → that row's dot
   segment gets `reverse=True`. The HEAD lane on rows below HEAD uses a
   slightly brighter colour for its `│` guide.
3. Return a `Strip`.

The widget computes its own width on every grid update:
`self.styles.width = max(min_width, min(max_width, num_lanes * 2 + 4))`.

### 6.3 Navigation handlers

- `action_cursor_up`: find the row of `cursor_sha`. Walk upward (`row-1`,
  `row-2`, …); first row whose `lane == cursor_lane` wins; if none, fall
  back to the nearest row in any lane. If `cursor_sha is None`, set it to
  the topmost commit. After moving, scroll if cursor leaves viewport.
- `action_cursor_down`: same, walking downward.
- `action_cursor_left` / `cursor_right`: find the nearest active lane on
  the requested side that has at least one row visible in the viewport;
  jump to that lane's earliest visible row.
- `action_refresh_repo`: call `self.repo.refresh()` (wipes caches), reload
  log + refs, rebuild grid, preserve `cursor_sha` if still present.

After every cursor change, post `CommitFocused(cursor_sha, screen_row)`.

### 6.4 Infinite scroll

When `action_cursor_down` lands within 5 rows of the bottom of the loaded
slice, schedule a background `repo.log(skip=len(commits))` call. When it
returns, append to commits, rebuild grid, preserve cursor.

### 6.5 Sticky BranchHeader

`branch_header.py`:

```python
class BranchHeader(Static):
    grid: reactive[GraphGrid | None] = reactive(None)
    scroll_y: reactive[int] = reactive(0)

    def render(self) -> RenderableType: ...
```

It is mounted as the first child of `GitHistoryWidget` and pinned with
`dock: top` in CSS so it does not scroll. It renders one line:
each lane's branch label (truncated to `lane_width - 1` chars). Updates
reactively when `grid` or `scroll_y` change. When the topmost visible
commit on a lane has a known branch label, use that; otherwise blank.

### 6.6 CommitDetailPopup

`popup.py`:

```python
class CommitDetailPopup(Static):
    commit: reactive[Commit | None] = reactive(None)
    stats: reactive[CommitStats | None] = reactive(None)

    def render(self) -> RenderableType: ...
```

CSS:
```
CommitDetailPopup {
    width: 32;
    height: 4;
    border: round #cdd6f4;
    background: #1e1e2e;
    color: #cdd6f4;
    display: none;
}
```

The popup is mounted once at screen level (sibling of `Horizontal#workspace`).
The app positions it via `styles.offset = (x, y)` in response to
`CommitFocused` messages.

---

## 7. App integration (`app.py`)

### 7.1 Constants
```python
SIDEBAR_ORDER: tuple[str, ...] = ("tree", "git", "settings")
SIDEBAR_SELECTORS: dict[str, str] = {
    "tree": "#sidebar-tree",
    "git": "#sidebar-git",
    "settings": "#sidebar-settings",
}
```

`JetApp` gains an instance attribute `self._sidebar_order` (initially the
class constant, possibly trimmed in `on_mount`).

### 7.2 compose

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

### 7.3 on_mount

```python
git_w = self.query_one("#sidebar-git", GitHistoryWidget)
if not git_w.repo.is_git_repo():
    await git_w.remove()
    self._sidebar_order = tuple(s for s in SIDEBAR_ORDER if s != "git")
else:
    self._sidebar_order = SIDEBAR_ORDER
    git_w.display = False
self.query_one("#sidebar-settings").display = False
```

`action_cycle_sidebars` and `action_toggle_sidebar` both reference
`self._sidebar_order` instead of the class constant `SIDEBAR_ORDER`.

### 7.4 Sidebar navigation routing

The existing `action_sidebar_{up,down,open,close}` handlers gain a git
branch at the top of each method:

```python
def action_sidebar_up(self) -> None:
    git = self._visible_git_sidebar()
    if git is not None:
        git.action_cursor_up()
        return
    # ...existing tree / settings branches
```

`action_sidebar_open` → `git.action_cursor_right()`.
`action_sidebar_close` → `git.action_cursor_left()`.

### 7.5 Shift+Tab routing

```python
def action_move_toggle(self) -> None:
    git = self._visible_git_sidebar()
    if git is not None and git.cursor_sha is not None:
        self._open_commit_buffer(git.cursor_sha)
        return
    # ...existing tree move toggle logic
```

`_open_commit_buffer(sha)`:
- Builds the formatted text via `commit_view.format_commit(repo, sha)`.
- Opens a `JetEditor(text=..., path=Path(f"<commit:{short}>"),
  config=..., read_only=True)` in a new `TabPane` titled
  `<commit:{short}>`.
- If a tab for this virtual path already exists, switch to it instead.

### 7.6 Popup synchronisation

```python
def on_descendant_focus(self, event) -> None:
    self._sync_git_popup()

def on_descendant_blur(self, event) -> None:
    self._sync_git_popup()

@on(GitHistoryWidget.CommitFocused)
def _on_commit_focused(self, event: GitHistoryWidget.CommitFocused) -> None:
    self._update_popup_content(event.sha)
    self._position_popup(event.row)
    self._sync_git_popup()
```

`_sync_git_popup` checks: git sidebar exists, is displayed, has focus, has
a cursor sha. If any condition fails, `popup.display = False`.

`_position_popup(row)` computes:
- `x = sidebar.region.right + 1`
- `y = sidebar.region.y + (row - scroll_y) + header_height`
- Flip `y -= popup.region.height` if it would overflow the screen.

### 7.7 `JetEditor` read_only flag

Patch `jet/editor.py` to accept a `read_only: bool = False` kwarg. When
true:
- Override key handlers that would insert/delete to no-op (or call
  `super()` only for cursor movement / selection / scroll).
- `action_save` notifies "read-only" and returns.
- The buffer still supports search, find-next, copy.

---

## 8. Error handling

| Condition | Behaviour |
|-----------|-----------|
| `git` not on PATH | `Repo.is_git_repo()` returns `False`; sidebar removed from DOM. App notifies once at startup if `.git` directory exists in workspace. |
| Subprocess timeout (5s) | Widget renders a single error row `error loading history`. Caches are not poisoned. `r` retries. |
| Encoding errors in messages/author | `errors="replace"` masks them. |
| Empty repo (no commits yet) | Widget shows `no commits yet` centred. No popup, no buffer. |
| Detached HEAD | HEAD glyph still drawn at HEAD's commit. No branch label on HEAD lane. |
| Workspace path lacks read permission for `.git` | Treated as not-a-repo. |
| Network-backed worktree (refs missing locally) | `for-each-ref` returns only what is local; the graph reflects only those refs. |

---

## 9. Performance budget

| Operation | Target |
|-----------|--------|
| Cold open, 500 commits, repo of <50k objects | ≤ 200 ms total (log ~50 ms, refs ~10 ms, layout ~20 ms, first render ~50 ms) |
| Cursor move (no I/O) | ≤ 16 ms |
| First popup display per commit (stats fetch) | ≤ 30 ms |
| Refresh (`r`) | ≤ 300 ms on large repos |

Caches:
- `stats`: LRU 1024.
- `full_message`: LRU 128.
- No persistent cache between sessions.

---

## 10. Testing

```
tests/git_history/
  __init__.py
  fixtures/
    make_repo.py            # helper to script real git repos in tmp_path
  test_repo.py              # subprocess-level tests; mostly against fixtures
  test_layout.py            # pure-function unit tests with synthetic commits
  test_widget.py            # Textual pilot snapshot + key tests
  test_integration.py       # end-to-end JetApp + real fixture repo
```

### 10.1 test_layout.py (primary safety net)

Cases:
- Linear history (1 lane, N commits).
- Single branch + merge back to main (2 lanes, diagonal join).
- Long-lived feature branch with no merge (2 lanes, persistent).
- Two simultaneous feature branches (3 lanes, alternating L/R).
- Octopus merge (3 parents → 3 lanes converge).
- Detached HEAD (no main fallback applied via head_branch).
- `main` missing, `master` present → fallback works.
- More than `MAX_LANES` simultaneously active → outermost lanes collapse
  into `…`.
- Synthetic dirty row prepended when `dirty=True`.

### 10.2 test_repo.py

Uses `fixtures/make_repo.py` (a thin helper that calls
`subprocess.run(["git", "init", ...])` etc. in `tmp_path`). Asserts that
`Repo.log`, `Repo.refs`, `Repo.stats`, `Repo.head`, `Repo.is_dirty` return
the expected dataclasses for known histories.

### 10.3 test_widget.py

Via Textual `App.run_test()` pilot:
- `Shift+Down` from HEAD lands on the next commit on the same lane.
- `Shift+Right` jumps to the visible lane on the right.
- `r` refreshes without losing cursor sha when the sha still exists.
- `Shift+Tab` posts the message and the app opens a tab whose id matches
  the expected virtual path.
- Popup hides when the editor regains focus.

### 10.4 test_integration.py

Builds a fixture repo with 3 branches and 1 merge, launches `JetApp`,
navigates with the keyboard, asserts popup content and buffer content.

---

## 11. Out of scope (explicit non-goals)

- No checkout, cherry-pick, revert, branch creation, or any mutating
  operation.
- No filtering by author or path.
- No fuzzy search inside the graph.
- No diff modal (deferred; the commit-detail buffer covers the use case).
- No persistent cache between sessions.
- No remote fetch / pull. Refreshes are local only.
- No fancy mouse interactions beyond click-to-select and scroll.
- No keybinding customisation surface beyond what already exists in
  `JetApp` (the new Shift+Up/Down/Left/Right bindings reuse the existing
  rebindable `sidebar_up`/`sidebar_down`/`sidebar_open`/`sidebar_close`
  ids).

---

## 12. Implementation order (recommended)

1. `repo.py` + `tests/git_history/test_repo.py` + `fixtures/make_repo.py`.
2. `layout.py` + `tests/git_history/test_layout.py` (largest test surface).
3. `widget.py` skeleton: render only, no nav, no popup.
4. Keyboard navigation + infinite scroll.
5. `popup.py` + app-level focus/position synchronisation.
6. `branch_header.py` sticky header.
7. `commit_view.py` + `JetEditor.read_only` patch + Shift+Tab routing.
8. `app.py` integration (compose, on_mount, sidebar cycling, action
   routing, message handler).
9. M4 (tags `◆`), M6 (dirty `✱`), M7 (mouse click).
10. CSS polish, snapshot tests, manual smoke test against `jet` itself.

---
