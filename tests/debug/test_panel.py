import pytest
from unittest.mock import AsyncMock, MagicMock

from textual.app import App, ComposeResult
from textual.widgets import Button

from jet.debug.controller import DebugState
from jet.debug.panel import DebugPanel


class _Harness(App):
    def __init__(self, controller):
        super().__init__()
        self._ctrl = controller

    def compose(self) -> ComposeResult:
        yield DebugPanel(self._ctrl, id="panel")


@pytest.mark.asyncio
async def test_panel_run_button_calls_controller_start():
    ctrl = MagicMock()
    ctrl.state = DebugState.IDLE
    ctrl.start = AsyncMock()
    app = _Harness(ctrl)
    async with app.run_test() as pilot:
        await pilot.click("#btn-run")
        await pilot.pause()
        ctrl.start.assert_awaited()


@pytest.mark.asyncio
async def test_panel_continue_button_disabled_when_not_paused():
    ctrl = MagicMock()
    ctrl.state = DebugState.IDLE
    app = _Harness(ctrl)
    async with app.run_test() as pilot:
        btn = app.query_one("#btn-continue", Button)
        assert btn.disabled is True


@pytest.mark.asyncio
async def test_panel_paused_event_updates_locals_table():
    from jet.debug.protocol import Paused
    ctrl = MagicMock()
    ctrl.state = DebugState.IDLE
    app = _Harness(ctrl)
    async with app.run_test() as pilot:
        panel = app.query_one(DebugPanel)
        ev = Paused(
            file="/tmp/x.py", line=10,
            locals={"a": "1", "b": "2"},
            globals={"__name__": "'__main__'"},
            stack=[{"file": "/tmp/x.py", "line": 10, "func": "main"}],
        )
        panel.handle_event(ev)
        await pilot.pause()
        # Locals table should contain 2 rows.
        from textual.widgets import DataTable
        table = app.query_one("#tbl-locals", DataTable)
        assert table.row_count == 2
