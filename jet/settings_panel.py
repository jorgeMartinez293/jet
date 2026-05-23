"""Settings sidebar — minimalist editor configuration panel.

Renders as a borderless option list matching the file tree aesthetic.
Navigated via app-level shift+arrow bindings (no internal focus).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.message import Message
from textual.widget import Widget
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from .themes import APP_THEMES, SYNTAX_THEMES as THEMES


@dataclass
class EditorConfig:
    theme_name: str = "neon"
    app_theme: str = "ansi-dark"
    indent_width: int = 4
    show_line_numbers: bool = True
    terminal_app: str = "Terminal"


_INDENT_VALUES: tuple[int, ...] = (2, 4, 8)
_LABEL_WIDTH = 12
_MIN_WIDTH = 18
_MAX_WIDTH = 60


class SettingsPanel(Widget):
    """Editor settings sidebar. Minimalist, transparent, tree-like."""

    DEFAULT_CSS = """
    SettingsPanel {
        width: 28;
        min-width: 18;
        max-width: 60;
        background: transparent;
        border-right: solid white;
        padding: 0 1;
        overflow-x: hidden;
        overflow-y: hidden;
    }
    SettingsPanel > #settings-scroll {
        background: transparent;
        scrollbar-size: 0 0;
    }
    SettingsPanel #settings-title {
        color: #7f8a99;
        padding: 0 0 1 0;
    }
    SettingsPanel #settings-list {
        background: transparent;
        background-tint: transparent;
        border: none;
        scrollbar-size: 0 0;
        color: #cdd6f4;
        padding: 0;
    }
    SettingsPanel #settings-list:focus {
        background: transparent;
        background-tint: transparent;
    }
    SettingsPanel #settings-list > .option-list--option {
        background: transparent;
        padding: 0;
    }
    SettingsPanel #settings-list > .option-list--option-highlighted {
        background: transparent;
        color: #ffffff;
        text-style: reverse;
    }
    SettingsPanel #settings-list:focus > .option-list--option-highlighted {
        background: transparent;
        color: #ffffff;
        text-style: reverse;
    }
    """

    class ConfigChanged(Message):
        def __init__(self, config: EditorConfig) -> None:
            super().__init__()
            self.config = config

    class EditTerminalRequested(Message):
        """Panel asks app to prompt the user for the terminal-app string."""

        def __init__(self, current: str) -> None:
            super().__init__()
            self.current = current

    can_focus = False

    def __init__(self, config: EditorConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="settings-scroll"):
            yield Static("settings", id="settings-title")
            yield OptionList(id="settings-list")

    def on_mount(self) -> None:
        self._refresh_options()

    # ------------------------------------------------------------------ config

    @property
    def config(self) -> EditorConfig:
        return self._config

    def set_config(self, config: EditorConfig) -> None:
        self._config = config
        self._refresh_options()

    # ------------------------------------------------------------------ navigation API (app-level)

    def move_up(self) -> None:
        ol = self._list()
        if ol.option_count:
            ol.action_cursor_up()

    def move_down(self) -> None:
        ol = self._list()
        if ol.option_count:
            ol.action_cursor_down()

    def cycle(self, direction: int) -> None:
        """Cycle highlighted setting forward (+1) or backward (-1)."""
        opt_id = self._highlighted_id()
        if opt_id is None:
            return
        if opt_id == "theme":
            values = list(THEMES)
            i = (values.index(self._config.theme_name) + direction) % len(values)
            self._config = replace(self._config, theme_name=values[i])
        elif opt_id == "bg":
            names = [textual for _display, textual in APP_THEMES]
            try:
                cur = names.index(self._config.app_theme)
            except ValueError:
                cur = 0
            i = (cur + direction) % len(names)
            self._config = replace(self._config, app_theme=names[i])
        elif opt_id == "indent":
            i = (_INDENT_VALUES.index(self._config.indent_width) + direction) % len(_INDENT_VALUES)
            self._config = replace(self._config, indent_width=_INDENT_VALUES[i])
        elif opt_id == "lines":
            self._config = replace(self._config, show_line_numbers=not self._config.show_line_numbers)
        elif opt_id == "term":
            self.post_message(self.EditTerminalRequested(self._config.terminal_app))
            return
        self._refresh_options()
        self.post_message(self.ConfigChanged(self._config))

    def activate(self) -> None:
        """Enter on highlighted row — opens terminal-app prompt; otherwise cycles."""
        opt_id = self._highlighted_id()
        if opt_id == "term":
            self.post_message(self.EditTerminalRequested(self._config.terminal_app))
        else:
            self.cycle(+1)

    def set_terminal_app(self, value: str) -> None:
        value = value.strip() or "Terminal"
        self._config = replace(self._config, terminal_app=value)
        self._refresh_options()
        self.post_message(self.ConfigChanged(self._config))

    # ------------------------------------------------------------------ internals

    def _list(self) -> OptionList:
        return self.query_one("#settings-list", OptionList)

    def _highlighted_id(self) -> str | None:
        ol = self._list()
        if ol.highlighted is None or ol.option_count == 0:
            return None
        return ol.get_option_at_index(ol.highlighted).id

    def _refresh_options(self) -> None:
        ol = self._list()
        prev = ol.highlighted
        ol.clear_options()
        rows = [
            ("theme", self._row("theme", self._config.theme_name)),
            ("bg", self._row("background", self._bg_display())),
            ("indent", self._row("indent", str(self._config.indent_width))),
            ("lines", self._row("lines", "on" if self._config.show_line_numbers else "off")),
            ("term", self._row("terminal", self._config.terminal_app)),
        ]
        for oid, text in rows:
            ol.add_option(Option(text, id=oid))
        ol.highlighted = prev if prev is not None else 0
        self._recompute_width(rows)

    def _recompute_width(self, rows: list[tuple[str, str]]) -> None:
        title_cells = len("settings")
        max_row = max((len(text) for _oid, text in rows), default=0)
        # +2 horizontal padding (1 left, 1 right), +1 border-right, +1 safety
        total = max(title_cells, max_row) + 4
        total = max(_MIN_WIDTH, min(_MAX_WIDTH, total))
        self.styles.width = total

    @staticmethod
    def _row(label: str, value: str) -> str:
        return f"{label:<{_LABEL_WIDTH}}{value}"

    def _bg_display(self) -> str:
        for display, textual in APP_THEMES:
            if textual == self._config.app_theme:
                return display
        return self._config.app_theme
