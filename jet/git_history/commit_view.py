"""Formatter that turns a commit into a plain-text read-only buffer body."""

from __future__ import annotations

from .repo import Repo


def format_commit(repo: Repo, sha: str) -> str:
    refs = repo.refs()
    matching_refs = [r for r in refs if r.target_sha == sha]
    stats = repo.stats(sha)
    full_msg = repo.full_message(sha)
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
