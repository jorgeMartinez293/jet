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
    assert grid.main_lane == (grid.num_lanes - 1) // 2


def test_master_fallback_when_no_main() -> None:
    c = _c("c1")
    refs = [Ref(name="master", kind="local", target_sha=c.sha)]
    grid = build_grid([c], refs, head_sha=c.sha, head_branch="master", dirty=False)
    assert grid.rows[0].branch_label == "master"


def test_detached_head_layout_does_not_crash() -> None:
    c2 = _c("c2", ("c1",))
    c1 = _c("c1", ())
    refs = [Ref(name="main", kind="local", target_sha=c1.sha)]
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
    assert grid.sha_to_row[c.sha] == 1


def test_merge_pre_reserves_parent_lane_before_parent_commit() -> None:
    # History (newest first):
    #   m  — merge with parents (p_main, p_feat)
    #   x  — unrelated commit on its own lane that arrives AFTER the merge but
    #         BEFORE p_feat. Without pre-reservation of p_feat's lane,
    #         allocator could place x on the lane that p_feat ought to occupy.
    #   p_feat — feature parent
    #   p_main — main parent (also parent of x)
    p_main = _c("p_main", ())
    p_feat = _c("p_feat", ("p_main",))
    x = _c("x", ("p_main",))
    m = _c("m", ("p_main", "p_feat"))
    refs = [Ref(name="main", kind="local", target_sha=m.sha)]
    # Order newest-first: m, x, p_feat, p_main
    grid = build_grid(
        [m, x, p_feat, p_main],
        refs,
        head_sha=m.sha,
        head_branch="main",
        dirty=False,
    )
    # After the merge, the lane for p_feat must already be reserved. So when
    # x arrives, it must be on a DIFFERENT lane than the one reserved for p_feat.
    lane_of_x = next(r.lane for r in grid.rows if r.commit and r.commit.sha == x.sha)
    lane_of_p_feat = next(r.lane for r in grid.rows if r.commit and r.commit.sha == p_feat.sha)
    assert lane_of_x != lane_of_p_feat
