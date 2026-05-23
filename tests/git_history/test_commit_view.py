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
