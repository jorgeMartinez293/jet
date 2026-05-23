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
