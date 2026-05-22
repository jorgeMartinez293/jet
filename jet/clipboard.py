"""macOS clipboard helpers using pbcopy/pbpaste.

Primary copy/paste flow is handled by the terminal emulator (iTerm2 / Terminal.app)
via Cmd+C / Cmd+V — those keystrokes never reach the TUI. These helpers are for
explicit editor actions like "copy current line" that need to push to the system
clipboard without a user selection.
"""

from __future__ import annotations

import shutil
import subprocess


def is_available() -> bool:
    return shutil.which("pbcopy") is not None and shutil.which("pbpaste") is not None


def copy(text: str) -> None:
    if not is_available():
        return
    subprocess.run(["pbcopy"], input=text, text=True, check=False)


def paste() -> str:
    if not is_available():
        return ""
    result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
    return result.stdout
