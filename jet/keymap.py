"""On-disk user keybindings stored at $XDG_CONFIG_HOME/jet/keybindings.json."""

from __future__ import annotations

import json
import os
from pathlib import Path


def keymap_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "jet" / "keybindings.json"


def load_user_keymap() -> dict[str, str]:
    path = keymap_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}


def save_user_keymap(keymap: dict[str, str]) -> None:
    path = keymap_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keymap, indent=2, sort_keys=True), encoding="utf-8")
