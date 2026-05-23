"""Pure functions that assign lanes and glyphs for the git graph sidebar."""

from __future__ import annotations

from dataclasses import dataclass
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


def build_grid(
    commits: list[Commit],
    refs: list[Ref],
    head_sha: str,
    head_branch: str | None,
    dirty: bool = False,
) -> GraphGrid:
    """Turn newest-first commits + refs into a renderable GraphGrid.

    Task 5 scope: linear history only. Task 6 will add branches, merges,
    dirty row, and main centring.
    """
    if not commits:
        return GraphGrid(rows=(), num_lanes=1, main_lane=0, sha_to_row={}, lane_to_branch={})

    main_branch_name = _choose_main_branch(refs, head_branch)
    tag_targets = {r.target_sha for r in refs if r.kind == "tag"}
    refs_by_sha: dict[str, list[Ref]] = {}
    for r in refs:
        refs_by_sha.setdefault(r.target_sha, []).append(r)

    raw_rows, lane_to_branch = _assign_lanes(commits, refs, main_branch_name, head_sha)

    if dirty and raw_rows:
        head_raw = next((r for r in raw_rows if r.commit and r.commit.sha == head_sha), raw_rows[0])
        raw_rows = [_RawRow(commit=None, lane=head_raw.lane), *raw_rows]

    # Centring: trivially zero-offset for a single lane.
    main_lane_raw = _lane_of_branch(lane_to_branch, main_branch_name)
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


def _lane_of_branch(lane_to_branch: dict[int, str], branch_name: str | None) -> int | None:
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
    """Single-pass lane assignment for linear (Task 5) history.

    Branch and merge logic land in Task 6.
    """
    active_lanes: dict[int, str] = {}
    lane_to_branch: dict[int, str] = {}
    rows: list[_RawRow] = []

    main_target_sha: str | None = None
    for r in refs:
        if r.kind == "local" and main_branch is not None and r.name == main_branch:
            main_target_sha = r.target_sha
            break
    if main_target_sha is not None:
        active_lanes[0] = main_target_sha
        lane_to_branch[0] = main_branch  # type: ignore[assignment]
    else:
        active_lanes[0] = head_sha

    new_lane_counter = 0  # used in Task 6 for alternating L/R

    for commit in commits:
        matching = [lane for lane, sha in active_lanes.items() if sha == commit.sha]
        if matching:
            lane = 0 if 0 in matching else matching[0]
            for extra in matching:
                if extra != lane:
                    del active_lanes[extra]
        else:
            lane = _open_new_lane(active_lanes, new_lane_counter)
            new_lane_counter += 1

        if commit.parents:
            active_lanes[lane] = commit.parents[0]
            # Task 6 extends this for additional parents.
        else:
            active_lanes.pop(lane, None)

        rows.append(_RawRow(commit=commit, lane=lane))

    return rows, lane_to_branch


def _open_new_lane(active: dict[int, str], counter: int) -> int:
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
    # Only real commit rows (commit is not None) count as prior occupants.
    if any(prev.commit is not None and prev.lane == raw.lane for prev in raw_rows[:idx]):
        return None
    return branch_name
