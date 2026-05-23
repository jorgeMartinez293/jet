"""Modal screens: fuzzy file finder, command palette, search, replace, goto line."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from . import finder


class _ModalBase(ModalScreen):
    DEFAULT_CSS = """
    _ModalBase {
        align: center top;
        background: transparent;
    }
    _ModalBase > Vertical {
        width: 70%;
        max-width: 90;
        margin-top: 2;
        padding: 0 1;
        background: transparent;
        border: solid #ffffff;
        height: auto;
    }
    _ModalBase Input {
        background: transparent;
        border: none;
        padding: 0 1;
        color: #e6e6e6;
    }
    _ModalBase Input:focus {
        border: none;
        background: transparent;
    }
    _ModalBase Input > .input--placeholder {
        color: #5f6a78;
    }
    _ModalBase OptionList {
        background: transparent;
        background-tint: transparent;
        border: none;
        scrollbar-size: 0 0;
        color: #cdd6f4;
    }
    _ModalBase OptionList:focus {
        border: none;
        background: transparent;
        background-tint: transparent;
    }
    _ModalBase OptionList > .option-list--option {
        background: transparent;
        padding: 0 1;
    }
    _ModalBase OptionList > .option-list--option-highlighted {
        background: transparent;
        color: #ffffff;
        text-style: reverse;
    }
    _ModalBase OptionList:focus > .option-list--option-highlighted {
        background: transparent;
        color: #ffffff;
        text-style: reverse;
    }
    """

    BINDINGS = [("escape", "dismiss_modal", "Cancel"), ("ctrl+c", "dismiss_modal", "Cancel")]

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class _PickerScreen(_ModalBase):
    """Input + filterable OptionList. Subclasses provide items via `_items()`."""

    INPUT_ID = "picker-input"
    LIST_ID = "picker-list"
    PLACEHOLDER = "Search…"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder=self.PLACEHOLDER, id=self.INPUT_ID)
            yield OptionList(id=self.LIST_ID)

    def on_mount(self) -> None:
        self._refresh("")
        self.query_one(f"#{self.INPUT_ID}", Input).focus()

    def _items(self, query: str) -> Iterable[tuple[str, str]]:
        """Yield (label, id) for current query. Override."""
        return ()

    def _refresh(self, query: str) -> None:
        ol = self.query_one(f"#{self.LIST_ID}", OptionList)
        ol.clear_options()
        any_added = False
        for label, oid in self._items(query):
            ol.add_option(Option(label, id=oid))
            any_added = True
        if any_added:
            ol.highlighted = 0

    def _result(self, option_id: str | None) -> Any:
        """Map option id → dismissal value. Override if needed."""
        return option_id

    @on(Input.Changed)
    def _on_picker_changed(self, event: Input.Changed) -> None:
        if event.input.id == self.INPUT_ID:
            self._refresh(event.value)

    @on(Input.Submitted)
    def _on_picker_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != self.INPUT_ID:
            return
        ol = self.query_one(f"#{self.LIST_ID}", OptionList)
        if ol.option_count and ol.highlighted is not None:
            opt = ol.get_option_at_index(ol.highlighted)
            self.dismiss(self._result(opt.id))

    @on(OptionList.OptionSelected)
    def _on_picker_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._result(event.option.id))

    def _on_key(self, event: events.Key) -> None:  # type: ignore[override]
        # Forward nav keys from input to option list.
        if event.key not in ("down", "up", "pagedown", "pageup"):
            return
        ol = self.query_one(f"#{self.LIST_ID}", OptionList)
        if ol.option_count == 0:
            return
        cur = ol.highlighted or 0
        last = ol.option_count - 1
        step = {"down": 1, "up": -1, "pagedown": 10, "pageup": -10}[event.key]
        ol.highlighted = max(0, min(cur + step, last))
        event.prevent_default()
        event.stop()


class FuzzyFinderScreen(_PickerScreen):
    """Ctrl+P — fuzzy search across workspace files. Returns selected Path or None."""

    DEFAULT_CSS = _ModalBase.DEFAULT_CSS + """
    FuzzyFinderScreen OptionList {
        height: auto;
        max-height: 20;
        background: $surface;
        border: none;
    }
    """

    INPUT_ID = "finder-input"
    LIST_ID = "finder-list"
    PLACEHOLDER = "Search files…"

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self._files: list[Path] = []

    def on_mount(self) -> None:
        self._files = finder.list_files(self.root)
        super().on_mount()

    def _items(self, query: str) -> Iterable[tuple[str, str]]:
        for path in finder.rank(query, self._files, self.root):
            yield str(path.relative_to(self.root)), str(path)

    def _result(self, option_id: str | None) -> Any:
        return Path(option_id) if option_id else None


class CommandPaletteScreen(_PickerScreen):
    """Cmd/Opt+P — searchable command palette. Returns selected command id or None."""

    DEFAULT_CSS = _ModalBase.DEFAULT_CSS + """
    CommandPaletteScreen OptionList {
        height: auto;
        max-height: 20;
        background: $surface;
        border: none;
    }
    """

    INPUT_ID = "palette-input"
    LIST_ID = "palette-list"
    PLACEHOLDER = "Command…"

    def __init__(self, commands: list[tuple[str, str]]) -> None:
        super().__init__()
        self._commands = commands

    def _items(self, query: str) -> Iterable[tuple[str, str]]:
        q = query.lower().strip()
        if not q:
            yield from self._commands
            return
        # Simple substring match; preserve declaration order.
        for label, cid in self._commands:
            if q in label.lower():
                yield label, cid


class KeybindingsScreen(_PickerScreen):
    """List of bindings; select one to rebind. Returns the binding id or None."""

    DEFAULT_CSS = _ModalBase.DEFAULT_CSS + """
    KeybindingsScreen OptionList {
        height: auto;
        max-height: 20;
        background: $surface;
        border: none;
    }
    """

    INPUT_ID = "keybindings-input"
    LIST_ID = "keybindings-list"
    PLACEHOLDER = "Search action…"

    def __init__(self, bindings: list[tuple[str, str, str]]) -> None:
        """bindings: list of (binding_id, description, current_key_display)."""
        super().__init__()
        self._entries = bindings

    def _items(self, query: str) -> Iterable[tuple[str, str]]:
        q = query.lower().strip()
        for bid, desc, key in self._entries:
            label = f"{desc:<28} {key}"
            if not q or q in desc.lower() or q in key.lower():
                yield label, bid


class KeyCaptureScreen(_ModalBase):
    """Capture a keystroke. Modifier-only keys are ignored. Press Enter to confirm.

    Returns the captured key string or None on cancel.
    """

    DEFAULT_CSS = _ModalBase.DEFAULT_CSS + """
    KeyCaptureScreen #capture-message {
        background: transparent;
        color: #e6e6e6;
        padding: 1 1 0 1;
        height: auto;
    }
    KeyCaptureScreen #capture-current {
        background: transparent;
        color: #9aa5b1;
        padding: 0 1 1 1;
        height: auto;
    }
    """

    MODIFIER_KEYS = frozenset(
        {
            "shift",
            "ctrl",
            "control",
            "alt",
            "meta",
            "super",
            "hyper",
            "shift_left",
            "shift_right",
            "ctrl_left",
            "ctrl_right",
            "alt_left",
            "alt_right",
            "meta_left",
            "meta_right",
            "super_left",
            "super_right",
        }
    )

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message
        self._pending: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._message, id="capture-message")
            yield Static("(no key pressed yet)", id="capture-current")

    def on_mount(self) -> None:
        self.focus()

    def _update_current(self) -> None:
        label = self._pending or "(no key pressed yet)"
        self.query_one("#capture-current", Static).update(label)

    def on_key(self, event: events.Key) -> None:
        event.prevent_default()
        event.stop()
        key = event.key
        if key in ("escape", "ctrl+c"):
            self.dismiss(None)
            return
        if key == "enter" and self._pending is not None:
            self.dismiss(self._pending)
            return
        if key in self.MODIFIER_KEYS:
            return
        self._pending = key
        self._update_current()


class GotoLineScreen(_ModalBase):
    """Ctrl+G — jump to a line number. Returns 0-based line index or None."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Go to line…", id="goto-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def on_submitted(self, event: Input.Submitted) -> None:
        try:
            line = int(event.value.strip())
        except ValueError:
            self.dismiss(None)
            return
        self.dismiss(max(0, line - 1))


class SaveAsScreen(_ModalBase):
    """Prompt for a filename when saving an untitled buffer. Returns name or None."""

    def __init__(self, initial: str = "") -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(value=self._initial, placeholder="File name…", id="saveas-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def on_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name:
            self.dismiss(name)
        else:
            self.dismiss(None)


class SearchScreen(_ModalBase):
    """Ctrl+F — find. Returns the query string or None."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Find…", id="search-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def on_submitted(self, event: Input.Submitted) -> None:
        value = event.value
        if value:
            self.dismiss(value)
        else:
            self.dismiss(None)


class ConfirmScreen(_ModalBase):
    """Confirmation prompt styled like the command palette. Returns the chosen id or None."""

    DEFAULT_CSS = _ModalBase.DEFAULT_CSS + """
    ConfirmScreen #confirm-message {
        background: transparent;
        color: #e6e6e6;
        padding: 0 1;
        height: auto;
    }
    ConfirmScreen OptionList {
        height: auto;
        background: transparent;
        border: none;
    }
    """

    LIST_ID = "confirm-list"

    def __init__(self, message: str, options: list[tuple[str, str]]) -> None:
        super().__init__()
        self._message = message
        self._options = options

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._message, id="confirm-message")
            yield OptionList(*[Option(label, id=oid) for label, oid in self._options], id=self.LIST_ID)

    def on_mount(self) -> None:
        ol = self.query_one(f"#{self.LIST_ID}", OptionList)
        ol.highlighted = 0
        ol.focus()

    @on(OptionList.OptionSelected)
    def _on_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)


class ReplaceScreen(_ModalBase):
    """Ctrl+H — replace. Returns (find, replace_with) or None."""

    DEFAULT_CSS = _ModalBase.DEFAULT_CSS + """
    ReplaceScreen Input { margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Find…", id="replace-find")
            yield Input(placeholder="Replace with…", id="replace-with")

    def on_mount(self) -> None:
        self.query_one("#replace-find", Input).focus()

    @on(Input.Submitted, "#replace-find")
    def on_find_submitted(self) -> None:
        self.query_one("#replace-with", Input).focus()

    @on(Input.Submitted, "#replace-with")
    def on_replace_submitted(self) -> None:
        find = self.query_one("#replace-find", Input).value
        repl = self.query_one("#replace-with", Input).value
        if find:
            self.dismiss((find, repl))
        else:
            self.dismiss(None)
