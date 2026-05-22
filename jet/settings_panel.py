"""Settings sidebar — editor configuration panel."""

from __future__ import annotations

from dataclasses import dataclass, replace

from textual import on
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Label, Select, Static, Switch

from .theme import THEMES


@dataclass
class EditorConfig:
    theme_name: str = "neon"
    indent_width: int = 4
    use_tabs: bool = False
    show_line_numbers: bool = True
    soft_wrap: bool = False
    debug_terminal_command: str = (
        'osascript -e \'tell application "LiquidTerminal" to do script "{cmd}"\''
    )


class SettingsPanel(Widget):
    """Editor settings sidebar."""

    DEFAULT_CSS = """
    SettingsPanel {
        width: 28;
        min-width: 18;
        max-width: 60;
        background: transparent;
        border-right: solid white;
        padding: 0 1;
    }
    SettingsPanel > #settings-scroll {
        background: transparent;
    }
    SettingsPanel #settings-title {
        color: #ffffff;
        text-style: bold;
        padding: 0 0 1 0;
    }
    SettingsPanel Label {
        color: #9aa5b1;
        padding: 1 0 0 0;
        height: auto;
    }
    SettingsPanel Select {
        width: 1fr;
    }
    SettingsPanel Switch {
        margin: 0;
        background: transparent;
    }
    """

    class ConfigChanged(Message):
        def __init__(self, config: EditorConfig) -> None:
            super().__init__()
            self.config = config

    def __init__(self, config: EditorConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="settings-scroll"):
            yield Static("⚙  Settings", id="settings-title")
            yield Label("Theme")
            yield Select(
                [(name, name) for name in THEMES],
                value=self._config.theme_name,
                id="sel-theme",
                allow_blank=False,
            )
            yield Label("Indent width")
            yield Select(
                [("2 spaces", 2), ("4 spaces", 4), ("8 spaces", 8)],
                value=self._config.indent_width,
                id="sel-indent",
                allow_blank=False,
            )
            yield Label("Use tabs")
            yield Switch(value=self._config.use_tabs, id="sw-tabs")
            yield Label("Line numbers")
            yield Switch(value=self._config.show_line_numbers, id="sw-lines")
            yield Label("Soft wrap")
            yield Switch(value=self._config.soft_wrap, id="sw-wrap")
            yield Label("Debug terminal command")
            yield Input(
                value=self._config.debug_terminal_command,
                id="inp-debug-cmd",
                placeholder='osascript -e \'tell application "X" to do script "{cmd}"\'',
            )

    @on(Select.Changed, "#sel-theme")
    def _on_theme(self, e: Select.Changed) -> None:
        if e.value is not Select.BLANK:
            self._config = replace(self._config, theme_name=str(e.value))
            self.post_message(self.ConfigChanged(self._config))

    @on(Select.Changed, "#sel-indent")
    def _on_indent(self, e: Select.Changed) -> None:
        if e.value is not Select.BLANK:
            self._config = replace(self._config, indent_width=int(e.value))
            self.post_message(self.ConfigChanged(self._config))

    @on(Switch.Changed, "#sw-tabs")
    def _on_tabs(self, e: Switch.Changed) -> None:
        self._config = replace(self._config, use_tabs=e.value)
        self.post_message(self.ConfigChanged(self._config))

    @on(Switch.Changed, "#sw-lines")
    def _on_lines(self, e: Switch.Changed) -> None:
        self._config = replace(self._config, show_line_numbers=e.value)
        self.post_message(self.ConfigChanged(self._config))

    @on(Switch.Changed, "#sw-wrap")
    def _on_wrap(self, e: Switch.Changed) -> None:
        self._config = replace(self._config, soft_wrap=e.value)
        self.post_message(self.ConfigChanged(self._config))

    @on(Input.Changed, "#inp-debug-cmd")
    def _on_debug_cmd(self, e: Input.Changed) -> None:
        self._config = replace(self._config, debug_terminal_command=e.value)
        self.post_message(self.ConfigChanged(self._config))
