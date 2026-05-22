"""JetEditor — Textual TextArea subclass with auto-close brackets and auto-indent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import TextArea

from . import brackets, indent
from .settings_panel import EditorConfig
from .syntax import detect_language
from .theme import THEMES


class JetEditor(TextArea):
    """Code editor widget. One instance per open buffer/tab."""

    class BreakpointToggleRequested(Message):
        def __init__(self, editor: "JetEditor", line: int) -> None:
            super().__init__()
            self.editor = editor
            self.line = line

    on_breakpoint_toggle_request: Any = None  # set by App; test hook

    def request_breakpoint_toggle(self, line_1based: int) -> None:
        if callable(self.on_breakpoint_toggle_request):
            self.on_breakpoint_toggle_request(line_1based)
        else:
            self.post_message(self.BreakpointToggleRequested(self, line_1based))

    async def _on_click(self, event) -> None:  # type: ignore[override]
        meta = getattr(event, "meta", False) or getattr(event, "alt", False)
        if meta:
            try:
                line0, _ = self.get_target_document_location(event)
            except Exception:
                await super()._on_click(event)
                return
            self.request_breakpoint_toggle(line0 + 1)
            event.stop()
            return
        await super()._on_click(event)

    DEFAULT_CSS = """
    JetEditor {
        background: transparent;
        border: none;
        padding: 0 1;
        scrollbar-background: transparent;
        scrollbar-background-hover: transparent;
        scrollbar-background-active: transparent;
        scrollbar-color: #3a3f4b;
        scrollbar-color-hover: #5a6270;
        scrollbar-color-active: #7a8290;
        scrollbar-size: 1 1;
    }
    JetEditor:focus {
        border: none;
    }
    """

    def __init__(
        self,
        text: str = "",
        *,
        path: Path | None = None,
        language: str | None = None,
        config: EditorConfig | None = None,
        **kwargs,
    ) -> None:
        cfg = config or EditorConfig()
        lang = language or (detect_language(path) if path else None)
        super().__init__(
            text=text,
            language=lang,
            soft_wrap=cfg.soft_wrap,
            tab_behavior="indent",
            show_line_numbers=cfg.show_line_numbers,
            **kwargs,
        )
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = cfg.theme_name
        self.indent_width = cfg.indent_width
        self.path: Path | None = path
        self._original_text: str = text
        self._use_tabs: bool = cfg.use_tabs
        self._breakpoints: frozenset[int] = frozenset()
        self._current_exec_line: int | None = None

    @property
    def breakpoints(self) -> frozenset[int]:
        return self._breakpoints

    def set_breakpoints(self, lines: set[int] | frozenset[int]) -> None:
        self._breakpoints = frozenset(lines)
        if self.is_mounted:
            self.refresh()

    @property
    def current_exec_line(self) -> int | None:
        return self._current_exec_line

    def set_current_exec_line(self, line: int | None) -> None:
        self._current_exec_line = line
        if self.is_mounted:
            if line is not None:
                self.scroll_cursor_visible(center=True)
            self.refresh()

    def gutter_marker_for_line(self, line_1based: int) -> Text | None:
        """Return a Rich Text marker for the gutter of `line_1based`, or None.

        Used by the gutter renderer and by tests. Picks theme accent colors
        for breakpoint (error) and current-exec (warning).
        """
        is_bp = line_1based in self._breakpoints
        is_cur = self._current_exec_line == line_1based
        if not (is_bp or is_cur):
            return None
        if is_cur:
            return Text("▶", style="bold yellow")
        return Text("●", style="red")

    def render_line(self, y):  # type: ignore[override]
        strip = super().render_line(y)
        try:
            line_index = self.scroll_offset.y + y
        except Exception:
            return strip
        marker = self.gutter_marker_for_line(line_index + 1)
        if marker is None:
            return strip
        from textual.strip import Strip
        from rich.segment import Segment
        from rich.style import Style
        segs = list(strip)
        if not segs:
            return strip
        first = segs[0]
        if not first.text:
            return strip
        marker_style = Style.parse(str(marker.style)) if marker.style else None
        if self.show_line_numbers:
            # Recolor existing line-number digits in the marker color; leave
            # the text content alone so digits remain readable.
            segs[0] = Segment(first.text, marker_style)
        else:
            # No line numbers: replace the first cell with the marker glyph.
            glyph = marker.plain
            tail = first.text[len(glyph):] if len(first.text) > len(glyph) else ""
            segs[0] = Segment(glyph + tail, marker_style)
        return Strip(segs, strip.cell_length)

    def apply_config(self, config: EditorConfig) -> None:
        self.theme = config.theme_name
        self.show_line_numbers = config.show_line_numbers
        self.soft_wrap = config.soft_wrap
        self.indent_width = config.indent_width
        self._use_tabs = config.use_tabs

    @property
    def modified(self) -> bool:
        return self.text != self._original_text

    def mark_saved(self) -> None:
        self._original_text = self.text

    def _line_text(self, row: int) -> str:
        try:
            return self.get_line(row).plain
        except IndexError:
            return ""

    def _current_line(self) -> str:
        row, _ = self.cursor_location
        return self._line_text(row)

    def _on_focus(self, event: events.Focus) -> None:
        super()._on_focus(event)
        driver = self.app._driver
        driver.write("\x1b[6 q")  # steady bar cursor
        driver.write("\x1b[?25h")  # show terminal cursor
        driver.flush()

    def _on_blur(self, event: events.Blur) -> None:
        super()._on_blur(event)
        driver = self.app._driver
        driver.write("\x1b[?25l")  # hide terminal cursor
        driver.flush()

    async def _on_key(self, event: events.Key) -> None:  # type: ignore[override]
        if self.read_only:
            return

        if event.key == "tab" and self._use_tabs:
            self.insert("\t", maintain_selection_offset=False)
            event.prevent_default()
            event.stop()
            return

        if event.key == "enter":
            if self._handle_enter():
                event.prevent_default()
                event.stop()
            return

        if event.key == "backspace":
            if self._handle_backspace():
                event.prevent_default()
                event.stop()
            return

        ch = event.character
        if not ch or len(ch) != 1:
            return

        if ch in brackets.OPENERS:
            if self._handle_opener(ch):
                event.prevent_default()
                event.stop()
            return

        if ch in brackets.CLOSERS:
            if self._handle_closer(ch):
                event.prevent_default()
                event.stop()
            return

    def _handle_opener(self, ch: str) -> bool:
        line = self._current_line()
        _, col = self.cursor_location

        if not self.selection.is_empty:
            closer = brackets.closer_for(ch)
            if closer is None:
                return False
            selected = self.selected_text
            self.replace(
                f"{ch}{selected}{closer}",
                self.selection.start,
                self.selection.end,
                maintain_selection_offset=False,
            )
            return True

        if not brackets.should_auto_close(line, col, ch):
            return False

        closer = brackets.closer_for(ch)
        if closer is None:
            return False
        self.insert(ch + closer, maintain_selection_offset=False)
        self.move_cursor_relative(columns=-1)
        return True

    def _handle_closer(self, ch: str) -> bool:
        line = self._current_line()
        _, col = self.cursor_location
        if brackets.should_skip_over(line, col, ch):
            self.move_cursor_relative(columns=1)
            return True
        return False

    def _handle_backspace(self) -> bool:
        if not self.selection.is_empty:
            return False
        line = self._current_line()
        row, col = self.cursor_location
        if brackets.should_delete_pair(line, col):
            self.delete((row, col - 1), (row, col + 1), maintain_selection_offset=False)
            return True
        return False

    def _handle_enter(self) -> bool:
        if not self.selection.is_empty:
            return False
        line = self._current_line()
        row, col = self.cursor_location
        prev_part = line[:col]
        next_char = line[col] if col < len(line) else ""

        indent_str = indent.compute_newline_indent(prev_part, self.language)

        if indent.should_open_block(prev_part, next_char):
            base = indent.leading_whitespace(prev_part)
            new_text = f"\n{indent_str}\n{base}"
            self.insert(new_text, maintain_selection_offset=False)
            # Cursor is now after closing newline+base on the last new line.
            # Move it up to the indented blank line, end of indent.
            self.move_cursor(location=(row + 1, len(indent_str)))
            return True

        self.insert("\n" + indent_str, maintain_selection_offset=False)
        return True
