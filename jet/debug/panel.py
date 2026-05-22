"""DebugPanel — sidebar widget that drives DebugController."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Collapsible, DataTable, Static

from jet.debug.controller import DebugController, DebugState
from jet.debug.protocol import Exception_, Exited, Paused


class DebugPanel(Widget):
    """Debug controls + variable inspection."""

    DEFAULT_CSS = """
    DebugPanel {
        width: 32;
        min-width: 24;
        max-width: 60;
        background: transparent;
        border-right: solid white;
        padding: 0 1;
    }
    DebugPanel #dbg-title {
        color: #ffffff;
        text-style: bold;
        padding: 0 0 1 0;
    }
    DebugPanel #dbg-status {
        color: #9aa5b1;
        padding: 0 0 1 0;
    }
    DebugPanel Button {
        margin: 0 1 1 0;
        min-width: 0;
    }
    DebugPanel DataTable {
        height: auto;
        max-height: 16;
        background: transparent;
    }
    """

    def __init__(self, controller: DebugController, **kw: Any) -> None:
        super().__init__(**kw)
        self._ctrl = controller

    def compose(self) -> ComposeResult:
        with ScrollableContainer():
            yield Static("🐞 Debug", id="dbg-title")
            with Horizontal():
                yield Button("▶ Run", id="btn-run", variant="success")
                yield Button("■ Stop", id="btn-stop", variant="error", disabled=True)
            with Horizontal():
                yield Button("⏵ Cont", id="btn-continue", disabled=True)
                yield Button("↷ Over", id="btn-over", disabled=True)
            with Horizontal():
                yield Button("↘ Into", id="btn-into", disabled=True)
                yield Button("↖ Out", id="btn-out", disabled=True)
            yield Static("Status: idle", id="dbg-status")
            with Collapsible(title="Locals", collapsed=False):
                t = DataTable(id="tbl-locals", show_header=True, zebra_stripes=True)
                t.add_columns("name", "value")
                yield t
            with Collapsible(title="Globals", collapsed=True):
                t = DataTable(id="tbl-globals", show_header=True, zebra_stripes=True)
                t.add_columns("name", "value")
                yield t
            with Collapsible(title="Breakpoints", collapsed=True):
                yield Static("(none)", id="bp-list")

    # ---- event sink invoked by the controller ----

    def handle_event(self, ev: Any) -> None:
        if isinstance(ev, Paused):
            self._refresh_state()
            self._fill_table("#tbl-locals", ev.locals)
            self._fill_table("#tbl-globals", ev.globals)
            self.query_one("#dbg-status", Static).update(
                f"Status: paused ({Path(ev.file).name}:{ev.line})"
            )
        elif isinstance(ev, Exited):
            self._refresh_state()
            self.query_one("#dbg-status", Static).update(f"Status: exited ({ev.code})")
            self._fill_table("#tbl-locals", {})
            self._fill_table("#tbl-globals", {})
        elif isinstance(ev, Exception_):
            self.query_one("#dbg-status", Static).update(
                f"Status: {ev.exc_type}: {ev.exc_value[:40]}"
            )
        else:
            self._refresh_state()

    def refresh_breakpoints(self, bp: dict[Path, set[int]]) -> None:
        lines: list[str] = []
        for f, s in bp.items():
            for ln in sorted(s):
                lines.append(f"{f.name}:{ln}")
        st = self.query_one("#bp-list", Static)
        st.update("\n".join(lines) if lines else "(none)")

    def _fill_table(self, selector: str, items: dict[str, str]) -> None:
        t = self.query_one(selector, DataTable)
        t.clear()
        for k, v in items.items():
            t.add_row(k, v)

    def _refresh_state(self) -> None:
        s = self._ctrl.state
        self.query_one("#btn-run", Button).disabled = s in (
            DebugState.RUNNING, DebugState.PAUSED, DebugState.STARTING
        )
        self.query_one("#btn-stop", Button).disabled = s in (
            DebugState.IDLE, DebugState.EXITED, DebugState.ERROR
        )
        for bid in ("btn-continue", "btn-over", "btn-into", "btn-out"):
            self.query_one(f"#{bid}", Button).disabled = s != DebugState.PAUSED

    # ---- buttons ----

    @on(Button.Pressed, "#btn-run")
    async def _run(self) -> None:
        await self._ctrl_start()

    async def _ctrl_start(self) -> None:
        # Filled in by App which knows the active editor + buffer.
        if callable(self.on_run_requested):
            await self.on_run_requested()
        else:
            # Fallback: directly invoke controller.start (used in tests where
            # no App wires on_run_requested).
            await self._ctrl.start()

    on_run_requested: Any = None
    on_stop_requested: Any = None

    @on(Button.Pressed, "#btn-stop")
    async def _stop(self) -> None:
        if callable(self.on_stop_requested):
            await self.on_stop_requested()

    @on(Button.Pressed, "#btn-continue")
    async def _cont(self) -> None:
        await self._ctrl.continue_()
        self._refresh_state()

    @on(Button.Pressed, "#btn-over")
    async def _over(self) -> None:
        await self._ctrl.step_over()
        self._refresh_state()

    @on(Button.Pressed, "#btn-into")
    async def _into(self) -> None:
        await self._ctrl.step_into()
        self._refresh_state()

    @on(Button.Pressed, "#btn-out")
    async def _out(self) -> None:
        await self._ctrl.step_out()
        self._refresh_state()
