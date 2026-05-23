"""Persist EditorConfig to $XDG_CONFIG_HOME/jet/config.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from .settings_panel import EditorConfig


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "jet" / "config.json"


def load_user_config() -> EditorConfig:
    """Return EditorConfig from disk, falling back to defaults for missing/invalid fields."""
    path = config_path()
    if not path.is_file():
        return EditorConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return EditorConfig()
    if not isinstance(data, dict):
        return EditorConfig()
    defaults = EditorConfig()
    kwargs: dict[str, object] = {}
    for f in fields(EditorConfig):
        if f.name not in data:
            continue
        value = data[f.name]
        expected = type(getattr(defaults, f.name))
        # bool is a subclass of int — check bool first to avoid 1/0 leaking in.
        if expected is bool and isinstance(value, bool):
            kwargs[f.name] = value
        elif expected is int and isinstance(value, int) and not isinstance(value, bool):
            kwargs[f.name] = value
        elif expected is str and isinstance(value, str):
            kwargs[f.name] = value
    return EditorConfig(**kwargs)  # type: ignore[arg-type]


def save_user_config(config: EditorConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2, sort_keys=True), encoding="utf-8")
