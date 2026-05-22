"""CLI entry point for `jet`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .app import JetApp, parse_path_with_line


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jet",
        description="Fast TUI text editor — mouse, syntax highlight, autoindent, autoclose.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to open. Use file:line[:col] to jump on open.",
    )
    p.add_argument("--version", action="version", version=f"jet {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths: list[Path] = []
    jumps: list[tuple[Path, int, int | None]] = []
    for raw in args.paths or ["."]:
        path, line, col = parse_path_with_line(raw)
        paths.append(path)
        if line is not None:
            jumps.append((path.resolve(), line, col))

    app = JetApp(paths=paths)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
