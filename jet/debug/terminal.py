"""Spawn an external terminal app running a given command."""

from __future__ import annotations

import shlex
import subprocess
import time


class TerminalSpawnError(RuntimeError):
    pass


def build_command(template: str, argv: list[str]) -> str:
    joined = " ".join(shlex.quote(a) for a in argv)
    return template.format(cmd=joined)


def spawn(template: str, argv: list[str]) -> None:
    """Launch the external terminal app with the runner command.

    Raises TerminalSpawnError if the spawn fails immediately.
    """
    cmd = build_command(template, argv)
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as e:
        raise TerminalSpawnError(f"Could not launch terminal: {e}") from e
    # Give osascript ~150ms to fail fast.
    time.sleep(0.15)
    rc = proc.poll()
    if rc not in (None, 0):
        _, err = proc.communicate(timeout=1)
        raise TerminalSpawnError(
            f"Terminal spawn exited {rc}: {err.decode('utf-8', errors='replace').strip()}"
        )
