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
