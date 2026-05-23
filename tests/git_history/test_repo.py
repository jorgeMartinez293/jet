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
