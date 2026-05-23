"""Run the active file in a new terminal window using an interpreter chosen from the extension."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


# Extension → argv prefix for an interpreter that can execute the file directly.
# Compiled-only languages (C, C++, Rust, ...) are intentionally absent.
_EXT_TO_INTERPRETER: dict[str, list[str]] = {
    ".py": ["python3"],
    ".js": ["node"],
    ".mjs": ["node"],
    ".cjs": ["node"],
    ".ts": ["npx", "ts-node"],
    ".rb": ["ruby"],
    ".sh": ["bash"],
    ".bash": ["bash"],
    ".zsh": ["zsh"],
    ".lua": ["lua"],
    ".pl": ["perl"],
    ".php": ["php"],
    ".r": ["Rscript"],
    ".dart": ["dart", "run"],
    ".go": ["go", "run"],
    ".swift": ["swift"],
    ".jl": ["julia"],
    ".groovy": ["groovy"],
    ".scala": ["scala"],
}


class RunError(Exception):
    """Raised when the file cannot be executed (unknown ext, unsupported platform, ...)."""


def _shebang_argv(path: Path) -> list[str] | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    parts = first[2:].strip().split()
    if not parts:
        return None
    # /usr/bin/env python3  →  drop /usr/bin/env, keep rest
    if parts[0].endswith("/env") and len(parts) > 1:
        return parts[1:]
    return parts


def interpreter_for(path: Path) -> list[str] | None:
    """Return argv prefix for an interpreter, or None if file is compiled/unknown."""
    shebang = _shebang_argv(path)
    if shebang:
        return shebang
    return _EXT_TO_INTERPRETER.get(path.suffix.lower())


def run_in_terminal(path: Path, terminal_app: str = "Terminal") -> None:
    """Open the chosen terminal app in a new window, cd to the file's dir, run interpreter.

    `terminal_app` may be an app name ("Terminal", "iTerm", "Ghostty") or an
    absolute path to a .app bundle. The command runs from a temporary `.sh`
    script and the window stays open after the program exits.
    """
    if not path.is_file():
        raise RunError(f"{path.name} does not exist on disk")

    argv = interpreter_for(path)
    if argv is None:
        raise RunError(f"No interpreter for {path.suffix or path.name}")

    if sys.platform != "darwin":
        raise RunError(f"Unsupported platform: {sys.platform}")

    cmd = " ".join(shlex.quote(p) for p in [*argv, path.name])
    workdir = shlex.quote(str(path.parent))
    script = (
        "#!/bin/bash\n"
        f"cd {workdir} || exit 1\n"
        "clear\n"
        f"{cmd}\n"
        "status=$?\n"
        "echo\n"
        'echo "[exit $status — press any key to close]"\n'
        "read -n 1 -s\n"
    )

    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".sh", prefix="jet-run-")
        with os.fdopen(fd, "w") as fh:
            fh.write(script)
        os.chmod(tmp_path, 0o755)
    except OSError as e:
        raise RunError(f"Could not write run script: {e}") from e

    app = terminal_app.strip() or "Terminal"
    try:
        subprocess.run(["open", "-a", app, tmp_path], check=True)
    except subprocess.CalledProcessError as e:
        raise RunError(f"Could not launch '{app}' (not installed?): {e}") from e
    except OSError as e:
        raise RunError(f"Could not launch terminal: {e}") from e
