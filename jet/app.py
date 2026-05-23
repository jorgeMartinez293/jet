"""Main Textual app — wires sidebar, tabs, editor, status bar and modals."""

from __future__ import annotations

import re
import shutil
from dataclasses import replace
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import DirectoryTree, Select, Static, TabbedContent, TabPane

from .config import load_user_config, save_user_config
from .editor import JetEditor
from .git_history.commit_view import format_commit
from .git_history.popup import CommitDetailPopup
from .git_history.widget import GitHistoryWidget
from .keymap import load_user_keymap, save_user_keymap
from .runner import RunError, run_in_terminal
from .screens import (
    CommandPaletteScreen,
    ConfirmScreen,
    FuzzyFinderScreen,
    GotoLineScreen,
    KeyCaptureScreen,
    KeybindingsScreen,
    ReplaceScreen,
    SaveAsScreen,
    SearchScreen,
)
from .settings_panel import EditorConfig, SettingsPanel
from .sidebar import JetTree
from .themes import APP_THEMES, CUSTOM_THEMES, SYNTAX_THEMES


# Sidebars cycled by Ctrl+B. Order = cycle order.
SIDEBAR_ORDER: tuple[str, ...] = ("tree", "git", "settings")
SIDEBAR_SELECTORS: dict[str, str] = {
    "tree": "#sidebar-tree",
    "git": "#sidebar-git",
    "settings": "#sidebar-settings",
}


class _StatusBar(Static):
    """Bottom status line: cursor location, language, modified flag."""

    text = reactive("")

    def render(self) -> str:
        return self.text


class _MatchCounter(Static):
    """Top-right find-match indicator (e.g. '3/12'). Hidden when no active search."""

    text = reactive("")

    def render(self) -> str:
        return self.text


class JetApp(App):
    """`jet` editor — file tree + tabs + editor."""

    CSS_PATH = "styles.tcss"
    TITLE = "jet"

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("meta+s", "save", "Save", priority=True, id="save"),
        Binding("ctrl+s", "save", "Save", show=False, priority=True),
        Binding("meta+w", "close_tab", "Close", priority=True, id="close_tab"),
        Binding("ctrl+w", "close_tab", "Close", show=False, priority=True),
        Binding("ctrl+n", "new_buffer", "New", show=False, priority=True, id="new_buffer"),
        Binding("meta+n", "new_buffer", "New", show=False, priority=True),
        Binding("meta+q", "quit", "Quit", priority=True, id="quit"),
        Binding("ctrl+b", "cycle_sidebars", "Switch sidebar", priority=True, id="cycle_sidebars"),
        Binding("ctrl+l", "toggle_sidebar", "Hide sidebar", priority=True, id="toggle_sidebar"),
        Binding("meta+p", "open_palette", "Palette", priority=True, id="open_palette"),
        Binding("ctrl+p", "open_palette", "Palette", show=False, priority=True),
        Binding("meta+o", "fuzzy_finder", "Find file", priority=True, id="fuzzy_finder"),
        Binding("meta+f", "find", "Find", priority=True, id="find"),
        Binding("meta+h", "replace", "Replace", priority=True, id="replace"),
        Binding("meta+g", "goto_line", "Goto", priority=True, id="goto_line"),
        Binding("f3", "find_next", "Next match", show=False, priority=True, id="find_next"),
        Binding("ctrl+up", "find_prev", "Prev match", show=False, priority=True, id="find_prev"),
        Binding("ctrl+pageup", "prev_tab", "Prev tab", show=False, priority=True, id="prev_tab"),
        Binding("ctrl+pagedown", "next_tab", "Next tab", show=False, priority=True, id="next_tab"),
        Binding("shift+up", "sidebar_up", "Sidebar up", show=False, priority=True, id="sidebar_up"),
        Binding("shift+down", "sidebar_down", "Sidebar down", show=False, priority=True, id="sidebar_down"),
        Binding("shift+right", "sidebar_open", "Sidebar open", show=False, priority=True, id="sidebar_open"),
        Binding("shift+left", "sidebar_close", "Sidebar close", show=False, priority=True, id="sidebar_close"),
        Binding("shift+tab", "move_toggle", "Grab/drop file", show=False, priority=True, id="move_toggle"),
        Binding("escape", "move_cancel", "Cancel move", show=False, priority=True, id="move_cancel"),
        Binding("backspace", "delete_file", "Delete grabbed file", show=False, priority=True, id="delete_file"),
        Binding("ctrl+shift+enter", "run_file", "Run file", priority=True, id="run_file"),
    ]

    def action_screenshot(self, *args, **kwargs) -> None:  # type: ignore[override]
        pass

    async def _check_bindings(self, key: str, priority: bool = False) -> bool:
        if isinstance(self.screen, KeyCaptureScreen):
            return False
        return await super()._check_bindings(key, priority)

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
        self._editor_config: EditorConfig = load_user_config()
        self._active_sidebar: str = SIDEBAR_ORDER[0]
        self._sidebar_order: tuple[str, ...] = SIDEBAR_ORDER
        self._moving_path: Path | None = None
        self._user_keymap: dict[str, str] = load_user_keymap()

    # ------------------------------------------------------------------ compose

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            yield JetTree(str(self.workspace), id="sidebar-tree")
            yield GitHistoryWidget(self.workspace, id="sidebar-git")
            yield SettingsPanel(self._editor_config, id="sidebar-settings")
            yield TabbedContent(id="tabs")
        yield _StatusBar(id="statusbar")
        yield _MatchCounter(id="match-counter")
        yield CommitDetailPopup(id="commit-popup")

    async def on_mount(self) -> None:
        for t in CUSTOM_THEMES:
            self.register_theme(t)
        # ansi-dark uses ANSI defaults → no opaque bg → terminal transparency shows through.
        self.theme = self._editor_config.app_theme
        if self._user_keymap:
            self.set_keymap(self._user_keymap)
        self.query_one("#sidebar-settings").display = False
        git_w = self.query_one("#sidebar-git", GitHistoryWidget)
        if not git_w.repo.is_git_repo():
            await git_w.remove()
            self._sidebar_order = tuple(s for s in SIDEBAR_ORDER if s != "git")
        else:
            git_w.display = False
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
            if path.is_file():
                data = path.read_bytes()
                if b"\x00" in data:
                    self.notify(
                        f"Unrecognized file format: {path.name}",
                        severity="warning",
                    )
                    return
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    self.notify(
                        f"Unrecognized file format: {path.name}",
                        severity="warning",
                    )
                    return
            else:
                text = ""
        except OSError as e:
            self.notify(f"Could not open {path.name}: {e}", severity="error")
            return

        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        editor = JetEditor(text=text, path=path, config=self._editor_config, id=f"ed-{self._tab_counter}")
        title = self._tab_title(path)
        await tabs.add_pane(TabPane(title, editor, id=tab_id))
        tabs.active = tab_id
        editor.focus()

    async def new_buffer(self) -> None:
        tabs = self.query_one(TabbedContent)
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        editor = JetEditor(text="", path=None, config=self._editor_config, id=f"ed-{self._tab_counter}")
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

    # ------------------------------------------------------------------ sidebars

    def _refocus_editor(self) -> None:
        """After layout-changing actions, return focus + caret to the editor.

        The editor draws its own caret; without this, key presses can land in
        the sidebar widget and the caret appears stuck.
        """
        ed = self._active_editor()
        if ed is None:
            return
        ed.focus()
        self.call_after_refresh(lambda: ed.scroll_cursor_visible())

    def action_toggle_sidebar(self) -> None:
        w = self.query_one(SIDEBAR_SELECTORS[self._active_sidebar])
        w.display = not w.display
        self._refocus_editor()

    def action_cycle_sidebars(self) -> None:
        cur = self._active_sidebar
        if cur not in self._sidebar_order:
            cur = self._sidebar_order[0]
            self._active_sidebar = cur
        cur_w = self.query_one(SIDEBAR_SELECTORS[cur])
        if not cur_w.display:
            cur_w.display = True
            self._refocus_editor()
            return
        cur_w.display = False
        nxt = self._sidebar_order[
            (self._sidebar_order.index(cur) + 1) % len(self._sidebar_order)
        ]
        self.query_one(SIDEBAR_SELECTORS[nxt]).display = True
        self._active_sidebar = nxt
        if nxt == "git":
            self.query_one("#sidebar-git", GitHistoryWidget).focus()
        else:
            self._refocus_editor()

    @on(DirectoryTree.NodeExpanded)
    @on(DirectoryTree.NodeCollapsed)
    def _on_tree_node_toggled(self, _event: object) -> None:
        # Tree auto-resizes its width on expand/collapse, which reflows the
        # editor. Textual hides the terminal cursor during the reflow render
        # and does not restore it without a focus event, so the caret vanishes
        # until the editor is interacted with. Re-focus after the resize
        # settles (two refreshes: one for _recompute_width, one for its layout
        # change) to resend the cursor-show escape and scroll caret into view.
        self.call_after_refresh(
            lambda: self.call_after_refresh(self._refocus_editor)
        )

    @on(SettingsPanel.ConfigChanged)
    def on_config_changed(self, event: SettingsPanel.ConfigChanged) -> None:
        prev_app_theme = self._editor_config.app_theme
        self._editor_config = event.config
        if event.config.app_theme != prev_app_theme:
            self.theme = event.config.app_theme
        for ed in self.query(JetEditor):
            ed.apply_config(event.config)
        try:
            save_user_config(event.config)
        except OSError as e:
            self.notify(f"Could not save settings: {e}", severity="error")

    @on(SettingsPanel.EditTerminalRequested)
    @work
    async def on_edit_terminal_requested(self, event: SettingsPanel.EditTerminalRequested) -> None:
        name = await self.push_screen_wait(SaveAsScreen(initial=event.current))
        if not isinstance(name, str) or not name:
            return
        panel = self.query_one("#sidebar-settings", SettingsPanel)
        panel.set_terminal_app(name)

    # ------------------------------------------------------------------ save/close

    @work
    async def action_save(self) -> None:
        ed = self._active_editor()
        if ed is None:
            return
        if ed.read_only:
            self.notify("Buffer is read-only")
            return
        if ed.path is None:
            if not await self._prompt_save_as(ed):
                return
        path = ed.path
        assert path is not None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(ed.text, encoding="utf-8")
            ed.mark_saved()
            self.notify(f"Saved {path.name}")
        except OSError as e:
            self.notify(f"Save failed: {e}", severity="error")
        self._update_status()

    async def _prompt_save_as(self, ed: JetEditor) -> bool:
        """Ask user for a filename for an untitled buffer. Returns True if path assigned."""
        name = await self.push_screen_wait(SaveAsScreen())
        if not name:
            return False
        candidate = Path(name).expanduser()
        target = (candidate if candidate.is_absolute() else self.workspace / candidate).resolve()
        if target.exists():
            self.notify(f"{target.name} already exists", severity="warning")
            return False
        ed.path = target
        self._relabel_editor_tab(ed, self._tab_title(target))
        return True

    def _relabel_editor_tab(self, ed: JetEditor, title: str) -> None:
        tabs = self.query_one(TabbedContent)
        for pane in tabs.query(TabPane):
            try:
                if pane.query_one(JetEditor) is ed and pane.id:
                    tabs.get_tab(pane.id).label = title
                    return
            except Exception:
                continue

    @work
    async def action_close_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        active = tabs.active
        if not active:
            return
        ed = self._active_editor()
        if ed is not None and ed.modified:
            name = ed.path.name if ed.path else "untitled"
            choice = await self.push_screen_wait(
                ConfirmScreen(
                    f"{name} has unsaved changes",
                    [("Save", "save"), ("Discard", "discard"), ("Cancel", "cancel")],
                )
            )
            if choice == "save":
                if ed.path is None:
                    if not await self._prompt_save_as(ed):
                        return
                path = ed.path
                assert path is not None
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(ed.text, encoding="utf-8")
                    ed.mark_saved()
                except OSError as e:
                    self.notify(f"Save failed: {e}", severity="error")
                    return
            elif choice != "discard":
                return
        await tabs.remove_pane(active)
        if tabs.tab_count == 0:
            await self.new_buffer()

    async def action_new_buffer(self) -> None:
        await self.new_buffer()

    @work
    async def action_run_file(self) -> None:
        ed = self._active_editor()
        if ed is None:
            return
        if ed.path is None:
            if not await self._prompt_save_as(ed):
                return
        path = ed.path
        assert path is not None
        if ed.modified or not path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(ed.text, encoding="utf-8")
                ed.mark_saved()
            except OSError as e:
                self.notify(f"Save failed: {e}", severity="error")
                return
            self._update_status()
        try:
            run_in_terminal(path, terminal_app=self._editor_config.terminal_app)
        except RunError as e:
            self.notify(str(e), severity="warning")

    # ------------------------------------------------------------------ palette

    @work
    async def action_open_palette(self) -> None:
        root = [
            ("Syntax themes…", "menu:syntax"),
            ("Background themes…", "menu:bg"),
            ("Keybindings…", "menu:keymap"),
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
        elif choice == "menu:keymap":
            await self._edit_keybindings()
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
        items = [(display, textual) for display, textual in APP_THEMES]
        picked = await self.push_screen_wait(CommandPaletteScreen(items))
        if isinstance(picked, str):
            self.theme = picked
            self._editor_config = replace(self._editor_config, app_theme=picked)
            try:
                save_user_config(self._editor_config)
            except OSError as e:
                self.notify(f"Could not save settings: {e}", severity="error")

    def _bindable_entries(self) -> list[tuple[str, str, str]]:
        """Return (binding_id, description, current_key) for each rebindable App binding."""
        entries: list[tuple[str, str, str]] = []
        for binding in self.BINDINGS:
            if not isinstance(binding, Binding) or binding.id is None:
                continue
            current = self._user_keymap.get(binding.id, binding.key)
            desc = binding.description or binding.action
            entries.append((binding.id, desc, current))
        return entries

    async def _edit_keybindings(self) -> None:
        while True:
            entries = self._bindable_entries()
            picked = await self.push_screen_wait(KeybindingsScreen(entries))
            if not isinstance(picked, str):
                return
            desc = next((d for bid, d, _ in entries if bid == picked), picked)
            new_key = await self.push_screen_wait(
                KeyCaptureScreen(
                    f"Press key combo for '{desc}'\n(Enter to confirm, Esc to cancel)"
                )
            )
            if not isinstance(new_key, str) or not new_key:
                continue
            self._user_keymap[picked] = new_key
            self.set_keymap(self._user_keymap)
            try:
                save_user_keymap(self._user_keymap)
            except OSError as e:
                self.notify(f"Could not save keymap: {e}", severity="error")
            self.notify(f"{desc} → {new_key}")

    # ------------------------------------------------------------------ find / goto

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
        self._find_step(result, direction=+1, from_cursor=True)

    @work
    async def action_find_next(self) -> None:
        await self._find_step_or_prompt(direction=+1)

    @work
    async def action_find_prev(self) -> None:
        await self._find_step_or_prompt(direction=-1)

    async def _find_step_or_prompt(self, *, direction: int) -> None:
        if not self._last_search:
            result = await self.push_screen_wait(SearchScreen())
            if not result:
                return
            self._last_search = result
            self._find_step(result, direction=direction, from_cursor=True)
            return
        self._find_step(self._last_search, direction=direction, from_cursor=False)

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

    # ------------------------------------------------------------------ tree navigation

    def _visible_sidebar_tree(self) -> JetTree | None:
        tree = self.query_one("#sidebar-tree", JetTree)
        return tree if tree.display else None

    def _visible_settings_panel(self) -> SettingsPanel | None:
        panel = self.query_one("#sidebar-settings", SettingsPanel)
        return panel if panel.display else None

    def _visible_git_sidebar(self) -> GitHistoryWidget | None:
        try:
            w = self.query_one("#sidebar-git", GitHistoryWidget)
        except Exception:
            return None
        return w if w.display else None

    @work
    async def _open_commit_buffer(self, sha: str) -> None:
        git = self._visible_git_sidebar()
        if git is None:
            return
        short = sha[:7]
        virtual_path = Path(f"<commit:{short}>")
        tabs = self.query_one(TabbedContent)
        for pane in tabs.query(TabPane):
            try:
                ed = pane.query_one(JetEditor)
            except Exception:
                continue
            if ed.path == virtual_path:
                tabs.active = pane.id or ""
                ed.focus()
                return
        text = format_commit(git.repo, sha)
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        editor = JetEditor(
            text=text,
            path=virtual_path,
            config=self._editor_config,
            read_only=True,
            id=f"ed-{self._tab_counter}",
        )
        await tabs.add_pane(TabPane(f"<commit:{short}>", editor, id=tab_id))
        tabs.active = tab_id
        editor.focus()

    # ------------------------------------------------------------------ git popup

    def on_descendant_focus(self, event) -> None:  # type: ignore[override]
        self._sync_git_popup()

    def on_descendant_blur(self, event) -> None:  # type: ignore[override]
        self._sync_git_popup()

    @on(GitHistoryWidget.CommitFocused)
    def _on_commit_focused(self, event: GitHistoryWidget.CommitFocused) -> None:
        git = self._visible_git_sidebar()
        if git is None or event.sha is None:
            return
        popup = self.query_one("#commit-popup", CommitDetailPopup)
        commit = next(
            (c for c in git._all_commits if c.sha == event.sha),
            None,
        )
        stats = git.repo.stats(event.sha) if commit is not None else None
        popup.set_commit(commit, stats)
        self._position_popup(event.row)
        self._sync_git_popup()

    def _position_popup(self, row: int) -> None:
        popup = self.query_one("#commit-popup", CommitDetailPopup)
        try:
            git = self.query_one("#sidebar-git", GitHistoryWidget)
        except Exception:
            return
        region = git.region
        scroll_y = git.scroll_offset.y
        header_height = 1
        x = region.right + 1
        y = region.y + header_height + (row - scroll_y)
        screen_h = self.size.height
        if y + 4 > screen_h:
            y = max(0, y - 4)
        popup.styles.offset = (x, y)

    def _sync_git_popup(self) -> None:
        try:
            popup = self.query_one("#commit-popup", CommitDetailPopup)
            git = self.query_one("#sidebar-git", GitHistoryWidget)
        except Exception:
            return
        visible = bool(
            git.display
            and git.has_focus
            and git.cursor_sha is not None
            and git.grid is not None
        )
        popup.display = visible

    def action_sidebar_up(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_up()
            return
        tree = self._visible_sidebar_tree()
        if tree is not None:
            tree.action_cursor_up()
            return
        panel = self._visible_settings_panel()
        if panel is not None:
            panel.move_up()

    def action_sidebar_down(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_down()
            return
        tree = self._visible_sidebar_tree()
        if tree is not None:
            tree.action_cursor_down()
            return
        panel = self._visible_settings_panel()
        if panel is not None:
            panel.move_down()

    async def action_sidebar_open(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_right()
            return
        tree = self._visible_sidebar_tree()
        if tree is not None:
            node = tree.cursor_node
            if node is None or node.data is None:
                return
            path = node.data.path
            if path.is_dir():
                if not node.is_expanded:
                    node.expand()
            elif self._moving_path is None:
                await self.open_file(path)
            return
        panel = self._visible_settings_panel()
        if panel is not None:
            panel.cycle(+1)

    def action_sidebar_close(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus:
            git.action_cursor_left()
            return
        tree = self._visible_sidebar_tree()
        if tree is not None:
            node = tree.cursor_node
            if node is None or node.data is None:
                return
            if node.data.path.is_dir() and node.is_expanded:
                node.collapse()
            elif node.parent is not None and node.parent.parent is not None:
                tree.select_node(node.parent)
            return
        panel = self._visible_settings_panel()
        if panel is not None:
            panel.cycle(-1)

    # ------------------------------------------------------------------ move mode

    def check_action(self, action: str, parameters):  # type: ignore[override]
        if action in ("move_cancel", "delete_file"):
            return self._moving_path is not None
        return True

    def action_move_toggle(self) -> None:
        git = self._visible_git_sidebar()
        if git is not None and git.has_focus and git.cursor_sha is not None:
            self._open_commit_buffer(git.cursor_sha)
            return
        tree = self._visible_sidebar_tree()
        if tree is None:
            return
        if self._moving_path is None:
            node = tree.cursor_node
            if node is None or node.data is None:
                return
            path = node.data.path
            if not (path.is_file() or path.is_dir()):
                return
            if node.parent is None:
                return
            self._moving_path = path
            tree.moving_path = path
            self.refresh_bindings()
            return
        node = tree.cursor_node
        if node is None or node.data is None:
            self._clear_move(tree)
            return
        cursor_path = node.data.path
        target_dir = cursor_path if cursor_path.is_dir() else cursor_path.parent
        src = self._moving_path
        src_resolved = src.resolve()
        target_resolved = target_dir.resolve()
        if src.is_dir() and src_resolved in target_resolved.parents:
            self.notify("Cannot move directory into itself", severity="error")
            return
        if src.is_dir() and target_resolved == src_resolved:
            self._clear_move(tree)
            return
        dest = target_dir / src.name
        if dest.resolve() == src_resolved:
            self._clear_move(tree)
            return
        if dest.exists():
            self.notify(f"{dest.name} already exists in {target_dir.name}", severity="error")
            return
        try:
            src.rename(dest)
        except OSError as e:
            self.notify(f"Move failed: {e}", severity="error")
            return
        for ed in self.query(JetEditor):
            if ed.path is None:
                continue
            try:
                rel = ed.path.resolve().relative_to(src_resolved)
            except ValueError:
                continue
            ed.path = dest if rel == Path(".") else dest / rel
        self._clear_move(tree)
        tree.reload()
        self.notify(f"Moved {src.name} → {target_dir}")

    def action_move_cancel(self) -> None:
        self._clear_move(self._visible_sidebar_tree())

    @work
    async def action_delete_file(self) -> None:
        if self._moving_path is None:
            return
        path = self._moving_path
        tree = self._visible_sidebar_tree()
        is_dir = path.is_dir()
        kind = "directory" if is_dir else "file"
        choice = await self.push_screen_wait(
            ConfirmScreen(
                f"Delete {kind} {path.name}? This cannot be undone.",
                [("Cancel", "cancel"), ("Delete", "delete")],
            )
        )
        if choice != "delete":
            return
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as e:
            self.notify(f"Delete failed: {e}", severity="error")
            return
        path_resolved = path.resolve()
        tabs = self.query_one(TabbedContent)
        for pane in list(tabs.query(TabPane)):
            try:
                ed = pane.query_one(JetEditor)
            except Exception:
                continue
            if ed.path is None:
                continue
            ed_resolved = ed.path.resolve()
            if ed_resolved == path_resolved or (is_dir and path_resolved in ed_resolved.parents):
                if pane.id:
                    await tabs.remove_pane(pane.id)
        self._clear_move(tree)
        if tabs.tab_count == 0:
            await self.new_buffer()
        if tree is not None:
            tree.reload()
        self.notify(f"Deleted {path.name}")

    def _clear_move(self, tree) -> None:
        self._moving_path = None
        if tree is not None:
            tree.moving_path = None
        self.refresh_bindings()

    # ------------------------------------------------------------------ tab nav

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

    @staticmethod
    def _all_match_offsets(text: str, needle: str) -> list[int]:
        if not needle:
            return []
        out: list[int] = []
        start = 0
        while True:
            idx = text.find(needle, start)
            if idx == -1:
                break
            out.append(idx)
            start = idx + len(needle)
        return out

    def _find_step(self, needle: str, *, direction: int, from_cursor: bool) -> None:
        ed = self._active_editor()
        if ed is None or not needle:
            self._hide_match_counter()
            return
        text = ed.text
        matches = self._all_match_offsets(text, needle)
        if not matches:
            self.notify(f"'{needle}' not found")
            self._hide_match_counter()
            return

        row, col = ed.cursor_location
        cur_off = self._location_to_offset(text, row, col)
        # When stepping prev after a previous find, cursor sits at the end of
        # the current match; anchor to selection start so we don't re-pick it.
        if direction < 0 and not from_cursor and not ed.selection.is_empty:
            sr, sc = ed.selection.start
            cur_off = self._location_to_offset(text, sr, sc)

        if direction > 0:
            ref = cur_off if from_cursor else cur_off + 1
            target = next((i for i, m in enumerate(matches) if m >= ref), None)
            if target is None:
                target = 0
        else:
            target = None
            for i in range(len(matches) - 1, -1, -1):
                if matches[i] < cur_off:
                    target = i
                    break
            if target is None:
                target = len(matches) - 1

        idx = matches[target]
        end_row, end_col = self._offset_to_location(text, idx + len(needle))
        start_row, start_col = self._offset_to_location(text, idx)
        ed.move_cursor(location=(end_row, end_col))
        ed.selection = ed.selection.__class__((start_row, start_col), (end_row, end_col))
        ed.scroll_cursor_visible(center=True)
        self._show_match_counter(target + 1, len(matches))

    def _show_match_counter(self, current: int, total: int) -> None:
        counter = self.query_one("#match-counter", _MatchCounter)
        counter.text = f"{current}/{total}"
        counter.display = True

    def _hide_match_counter(self) -> None:
        counter = self.query_one("#match-counter", _MatchCounter)
        counter.text = ""
        counter.display = False

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


# ---------------------------------------------------------------------- cli arg parsing


_LINE_RE = re.compile(r"^(.*?):(\d+)(?::(\d+))?$")


def parse_path_with_line(arg: str) -> tuple[Path, int | None, int | None]:
    """Accept `file.py`, `file.py:42`, or `file.py:42:7`."""
    m = _LINE_RE.match(arg)
    if not m:
        return Path(arg), None, None
    return Path(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None
