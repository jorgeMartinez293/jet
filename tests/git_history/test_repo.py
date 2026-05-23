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


def test_log_parses_merge_parents(tmp_path: Path) -> None:
    repo_path = init_repo(tmp_path / "r")
    commit(repo_path, "base")
    branch(repo_path, "feature")
    commit(repo_path, "feat-1", file="feat.txt")
    checkout(repo_path, "main")
    commit(repo_path, "main-1", file="main.txt")
    merge(repo_path, "feature")
    commits = Repo(repo_path).log(limit=10)
    merge_commit = commits[0]  # newest = the merge
    assert len(merge_commit.parents) == 2
    other_parent_subjects = {c.subject for c in commits[1:]}
    assert "feat-1" in other_parent_subjects
    assert "main-1" in other_parent_subjects
