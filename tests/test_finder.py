from pathlib import Path

from jet import finder


def _make_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hi')")
    (root / "src" / "util.py").write_text("def x(): ...")
    (root / "README.md").write_text("# Hello")
    (root / ".gitignore").write_text("ignored/\n")
    (root / "ignored").mkdir()
    (root / "ignored" / "secret.py").write_text("nope")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.cpython-311.pyc").write_text("")


def test_list_files_respects_gitignore_and_defaults(tmp_path: Path):
    _make_tree(tmp_path)
    files = finder.list_files(tmp_path)
    names = {str(p.relative_to(tmp_path)) for p in files}
    assert "src/main.py" in names
    assert "src/util.py" in names
    assert "README.md" in names
    assert "ignored/secret.py" not in names
    assert "__pycache__/x.cpython-311.pyc" not in names


def test_rank_orders_by_match(tmp_path: Path):
    _make_tree(tmp_path)
    files = finder.list_files(tmp_path)
    ranked = finder.rank("main", files, tmp_path)
    assert ranked[0].name == "main.py"


def test_rank_empty_query_returns_files(tmp_path: Path):
    _make_tree(tmp_path)
    files = finder.list_files(tmp_path)
    assert finder.rank("", files, tmp_path) == files[:50]
