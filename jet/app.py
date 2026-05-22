"""Main Textual app — wires sidebar, tabs, editor, status bar and modals."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import DirectoryTree, Select, Static, TabbedContent, TabPane

from .debug.controller import DebugController
from .debug.panel import DebugPanel
from .debug.protocol import Exception_, Exited, Paused
from .editor import JetEditor
from .screens import (
    CommandPaletteScreen,
    FuzzyFinderScreen,
    GotoLineScreen,
    ReplaceScreen,
    SearchScreen,
)
from .settings_panel import EditorConfig, SettingsPanel
from .sidebar import JetTree
from .theme import THEMES as SYNTAX_THEMES


class _StatusBar(Static):
    """Bottom status line: cursor location, language, modified flag."""

    text = reactive("")

    def render(self) -> str:
        return self.text


class JetApp(App):
    """`jet` editor — file tree + tabs + editor."""

    CSS_PATH = "styles.tcss"
    TITLE = "jet"

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("meta+s", "save", "Save"),
        Binding("ctrl+s", "save", "Save", show=False, priority=True),
        Binding("meta+w", "close_tab", "Close"),
        Binding("meta+q", "quit", "Quit"),
        Binding("ctrl+b", "cycle_sidebars", "Switch sidebar", priority=True),
        Binding("ctrl+l", "toggle_sidebar", "Hide sidebar", priority=True),
        Binding("meta+p", "open_palette", "Palette"),
        Binding("ctrl+p", "open_palette", "Palette", show=False, priority=True),
        Binding("meta+o", "fuzzy_finder", "Find file"),
        Binding("meta+f", "find", "Find"),
        Binding("meta+h", "replace", "Replace"),
        Binding("meta+g", "goto_line", "Goto"),
        Binding("f3", "find_next", "Next match", show=False),
        Binding("ctrl+pageup", "prev_tab", "Prev tab", show=False),
        Binding("ctrl+pagedown", "next_tab", "Next tab", show=False),
        Binding("shift+up", "sidebar_up", "Sidebar up", show=False, priority=True),
        Binding("shift+down", "sidebar_down", "Sidebar down", show=False, priority=True),
        Binding("shift+right", "sidebar_open", "Sidebar open", show=False, priority=True),
    ]

    def action_screenshot(self, *args, **kwargs) -> None:  # type: ignore[override]
        pass

    def __init__(self, paths: list[Path]) -> None:
        super().__init__()
        # Determine workspace root and initial files to open.
        self._initial_paths: list[Path] = []
        roots: list[Path] = []
        for p in paths:
            p = p.resolve()
            if p.is_dir():
                roots.append(p)
            elif p.is_file():
                self._initial_paths.append(p)
                roots.append(p.parent)
            else:
                # New file — treat as a file to create on save.
                self._initial_paths.append(p)
                roots.append(p.parent if p.parent.exists() else Path.cwd())
        self.workspace: Path = roots[0] if roots else Path.cwd()
        self._tab_counter: int = 0
        self._last_search: str | None = None
        self._editor_config: EditorConfig = EditorConfig()
        self._active_sidebar: str = "tree"  # "tree" or "settings"
        self.debug_controller = DebugController(on_event=self._on_debug_event)

    # ------------------------------------------------------------------ compose

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            yield JetTree(str(self.workspace), id="sidebar-tree")
            yield SettingsPanel(self._editor_config, id="sidebar-settings")
            yield DebugPanel(self.debug_controller, id="sidebar-debug")
            yield TabbedContent(id="tabs")
        yield _StatusBar(id="statusbar")

    async def on_mount(self) -> None:
        # ansi-dark uses ANSI defaults → no opaque bg → terminal transparency shows through.
        self.theme = "ansi-dark"
        self.query_one("#sidebar-settings").display = False
        self.query_one("#sidebar-debug").display = False
        panel = self.query_one(DebugPanel)
        panel.on_run_requested = self._debug_run
        panel.on_stop_requested = self.debug_controller.stop
        if self._initial_paths:
            for p in self._initial_paths:
                await self.open_file(p)
        else:
            await self.new_buffer()
        self._update_status()

    # ------------------------------------------------------------------ buffers

    async def open_file(self, path: Path) -> None:
        path = path.resolve()
        # If already open, just switch.
        tabs = self.query_one(TabbedContent)
        for pane in tabs.query(TabPane):
            ed = pane.query_one(JetEditor)
            if ed.path == path:
                tabs.active = pane.id or ""
                ed.focus()
                return

        try:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
        except OSError as e:
            self.notify(f"Could not open {path.name}: {e}", severity="error")
            return

        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        editor = JetEditor(text=text, path=path, config=self._editor_config, id=f"ed-{self._tab_counter}")
        editor.on_breakpoint_toggle_request = lambda line, e=editor: self._toggle_bp(e, line)
        title = self._tab_title(path)
        await tabs.add_pane(TabPane(title, editor, id=tab_id))
        tabs.active = tab_id
        editor.focus()

    async def new_buffer(self) -> None:
        tabs = self.query_one(TabbedContent)
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        editor = JetEditor(text="", path=None, config=self._editor_config, id=f"ed-{self._tab_counter}")
        editor.on_breakpoint_toggle_request = lambda line, e=editor: self._toggle_bp(e, line)
        await tabs.add_pane(TabPane("untitled", editor, id=tab_id))
        tabs.active = tab_id
        editor.focus()

    def _active_editor(self) -> JetEditor | None:
        tabs = self.query_one(TabbedContent)
        active = tabs.active
        if not active:
            return None
        try:
            pane = tabs.get_pane(active)
        except Exception:
            return None
        if pane is None:
            return None
        try:
            return pane.query_one(JetEditor)
        except Exception:
            return None

    @staticmethod
    def _tab_title(path: Path) -> str:
        return path.name or str(path)

    # ------------------------------------------------------------------ debug

    async def _debug_run(self) -> None:
        ed = self._active_editor()
        if ed is None:
            self.notify("No active editor", severity="warning")
            return
        if ed.path is None or ed.path.suffix != ".py":
            buf_text = ed.text if ed.path is None or ed.modified else None
            target = ed.path or self.workspace / "untitled.py"
        else:
            buf_text = ed.text if ed.modified else None
            target = ed.path
        try:
            await self.debug_controller.start(
                target=target,
                buffer_text=buf_text,
                terminal_template=self._editor_config.debug_terminal_command,
            )
        except Exception as e:
            self.notify(f"Could not start debug: {e}", severity="error")

    def _on_debug_event(self, ev) -> None:
        panel = self.query_one(DebugPanel)
        panel.handle_event(ev)
        panel.refresh_breakpoints(self.debug_controller.breakpoints)
        ed = self._active_editor()
        if ed is None:
            return
        if isinstance(ev, Paused):
            if ed.path is not None and str(ed.path) == ev.file:
                ed.set_current_exec_line(ev.line)
                ed.read_only = True
        elif isinstance(ev, (Exited, Exception_)):
            ed.set_current_exec_line(None)
            ed.read_only = False

    def _toggle_bp(self, editor, line: int) -> None:
        if editor.path is None:
            self.notify("Save the buffer before setting breakpoints", severity="warning")
            return
        self.debug_controller.toggle_breakpoint(editor.path, line)
        editor.set_breakpoints(self.debug_controller.get_breakpoints(editor.path))
        panel = self.query_one(DebugPanel)
        panel.refresh_breakpoints(self.debug_controller.breakpoints)

    # ------------------------------------------------------------------ events

    @on(DirectoryTree.FileSelected)
    async def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        await self.open_file(event.path)

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self) -> None:
        ed = self._active_editor()
        if ed is not None:
            ed.focus()
        self._update_status()

    def on_idle(self) -> None:  # type: ignore[override]
        self._update_status()

    # ------------------------------------------------------------------ actions

    def action_toggle_sidebar(self) -> None:
        sid = {"tree": "#sidebar-tree", "settings": "#sidebar-settings", "debug": "#sidebar-debug"}[
            self._active_sidebar
        ]
        w = self.query_one(sid)
        w.display = not w.display

    def action_cycle_sidebars(self) -> None:
        order = ["tree", "settings", "debug"]
        ids = {"tree": "#sidebar-tree", "settings": "#sidebar-settings", "debug": "#sidebar-debug"}
        cur = self._active_sidebar
        cur_w = self.query_one(ids[cur])
        if not cur_w.display:
            cur_w.display = True
            return
        cur_w.display = False
        nxt = order[(order.index(cur) + 1) % len(order)]
        self.query_one(ids[nxt]).display = True
        self._active_sidebar = nxt

    @on(SettingsPanel.ConfigChanged)
    def on_config_changed(self, event: SettingsPanel.ConfigChanged) -> None:
        self._editor_config = event.config
        for ed in self.query(JetEditor):
            ed.apply_config(event.config)

    async def action_save(self) -> None:
        ed = self._active_editor()
        if ed is None:
            return
        if ed.path is None:
            self.notify("No path for this buffer (untitled).", severity="warning")
            return
        try:
            ed.path.parent.mkdir(parents=True, exist_ok=True)
            ed.path.write_text(ed.text, encoding="utf-8")
            ed.mark_saved()
            self.notify(f"Saved {ed.path.name}")
        except OSError as e:
            self.notify(f"Save failed: {e}", severity="error")
        self._update_status()

    async def action_close_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        active = tabs.active
        if not active:
            return
        await tabs.remove_pane(active)
        if tabs.tab_count == 0:
            await self.new_buffer()

    @work
    async def action_open_palette(self) -> None:
        root = [
            ("Syntax themes…", "menu:syntax"),
            ("Background themes…", "menu:bg"),
            ("Toggle sidebar", "act:toggle_sidebar"),
            ("Switch sidebar panel", "act:cycle_sidebars"),
            ("Quit", "act:quit"),
        ]
        choice = await self.push_screen_wait(CommandPaletteScreen(root))
        if not isinstance(choice, str):
            return
        if choice == "menu:syntax":
            await self._pick_syntax_theme()
        elif choice == "menu:bg":
            await self._pick_background_theme()
        elif choice == "act:toggle_sidebar":
            self.action_toggle_sidebar()
        elif choice == "act:cycle_sidebars":
            self.action_cycle_sidebars()
        elif choice == "act:quit":
            self.exit()

    async def _pick_syntax_theme(self) -> None:
        items = [(name, name) for name in SYNTAX_THEMES]
        picked = await self.push_screen_wait(CommandPaletteScreen(items))
        if not isinstance(picked, str):
            return
        sel = self.query_one("#sel-theme", Select)
        if sel.value != picked:
            sel.value = picked
        else:
            self._editor_config = replace(self._editor_config, theme_name=picked)
            for ed in self.query(JetEditor):
                ed.apply_config(self._editor_config)

    async def _pick_background_theme(self) -> None:
        items: list[tuple[str, str]] = [("transparent (default)", "ansi-dark")]
        for name in sorted(self.available_themes):
            if name != "ansi-dark":
                items.append((name, name))
        picked = await self.push_screen_wait(CommandPaletteScreen(items))
        if isinstance(picked, str):
            self.theme = picked

    @work
    async def action_fuzzy_finder(self) -> None:
        selected = await self.push_screen_wait(FuzzyFinderScreen(self.workspace))
        if isinstance(selected, Path):
            await self.open_file(selected)

    @work
    async def action_find(self) -> None:
        result = await self.push_screen_wait(SearchScreen())
        if not result:
            return
        self._last_search = result
        self._find_next(result)

    def action_find_next(self) -> None:
        if self._last_search:
            self._find_next(self._last_search)

    @work
    async def action_replace(self) -> None:
        result = await self.push_screen_wait(ReplaceScreen())
        if not result:
            return
        find, repl = result
        ed = self._active_editor()
        if ed is None or not find:
            return
        count = ed.text.count(find)
        if count == 0:
            self.notify(f"'{find}' not found")
            return
        ed.text = ed.text.replace(find, repl)
        self.notify(f"Replaced {count} occurrence(s)")

    @work
    async def action_goto_line(self) -> None:
        result = await self.push_screen_wait(GotoLineScreen())
        if result is None:
            return
        ed = self._active_editor()
        if ed is None:
            return
        row = max(0, min(result, ed.document.line_count - 1))
        ed.move_cursor(location=(row, 0))
        ed.scroll_cursor_visible(center=True)

    def _visible_sidebar_tree(self) -> JetTree | None:
        tree = self.query_one("#sidebar-tree", JetTree)
        return tree if tree.display else None

    def action_sidebar_up(self) -> None:
        tree = self._visible_sidebar_tree()
        if tree is not None:
            tree.action_cursor_up()

    def action_sidebar_down(self) -> None:
        tree = self._visible_sidebar_tree()
        if tree is not None:
            tree.action_cursor_down()

    async def action_sidebar_open(self) -> None:
        tree = self._visible_sidebar_tree()
        if tree is None:
            return
        node = tree.cursor_node
        if node is None or node.data is None:
            return
        path = node.data.path
        if path.is_dir():
            if node.is_expanded:
                node.collapse()
            else:
                node.expand()
        else:
            await self.open_file(path)

    def action_prev_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        ids = [p.id for p in tabs.query(TabPane) if p.id]
        if not ids or not tabs.active:
            return
        i = ids.index(tabs.active)
        tabs.active = ids[(i - 1) % len(ids)]

    def action_next_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        ids = [p.id for p in tabs.query(TabPane) if p.id]
        if not ids or not tabs.active:
            return
        i = ids.index(tabs.active)
        tabs.active = ids[(i + 1) % len(ids)]

    # ------------------------------------------------------------------ search

    def _find_next(self, needle: str) -> None:
        ed = self._active_editor()
        if ed is None or not needle:
            return
        text = ed.text
        # Compute absolute cursor offset.
        row, col = ed.cursor_location
        offset = self._location_to_offset(text, row, col)
        idx = text.find(needle, offset + 1)
        if idx == -1:
            idx = text.find(needle)
            if idx == -1:
                self.notify(f"'{needle}' not found")
                return
            self.notify("Wrapped to top")
        end_row, end_col = self._offset_to_location(text, idx + len(needle))
        start_row, start_col = self._offset_to_location(text, idx)
        ed.selection = ed.selection.__class__((start_row, start_col), (end_row, end_col))
        ed.move_cursor(location=(end_row, end_col))
        ed.scroll_cursor_visible(center=True)

    @staticmethod
    def _location_to_offset(text: str, row: int, col: int) -> int:
        lines = text.split("\n")
        return sum(len(l) + 1 for l in lines[:row]) + col

    @staticmethod
    def _offset_to_location(text: str, offset: int) -> tuple[int, int]:
        before = text[:offset]
        row = before.count("\n")
        last_nl = before.rfind("\n")
        col = offset - (last_nl + 1) if last_nl >= 0 else offset
        return row, col

    # ------------------------------------------------------------------ status

    def _update_status(self) -> None:
        bar = self.query_one(_StatusBar)
        ed = self._active_editor()
        if ed is None:
            bar.text = ""
            return
        row, col = ed.cursor_location
        lang = ed.language or "plain"
        modified = "*" if ed.modified else " "
        name = ed.path.name if ed.path else "untitled"
        bar.text = f"{modified} {name}    {lang}    {row + 1}:{col + 1}"


_LINE_RE = re.compile(r"^(.*?):(\d+)(?::(\d+))?$")


def parse_path_with_line(arg: str) -> tuple[Path, int | None, int | None]:
    """Accept `file.py`, `file.py:42`, or `file.py:42:7`."""
    m = _LINE_RE.match(arg)
    if not m:
        return Path(arg), None, None
    return Path(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None
