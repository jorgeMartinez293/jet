import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from jet.debug.controller import DebugController, DebugState


FIXTURE = Path(__file__).parent / "fixtures" / "simple.py"


_PROC_TASKS: list[asyncio.Task] = []


def _make_fake_spawn() -> "callable":  # type: ignore[type-arg]
    def fake_spawn(_template: str, argv: list[str]) -> None:
        del _template
        _PROC_TASKS.append(
            asyncio.create_task(
                asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            )
        )

    return fake_spawn


async def _drain_procs() -> None:
    while _PROC_TASKS:
        task = _PROC_TASKS.pop()
        proc = await task
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()


@pytest.mark.asyncio
async def test_controller_start_runs_through_to_exited():
    """End-to-end with the real runner — terminal spawn replaced by raw subprocess."""
    events: list = []

    def on_event(ev):
        events.append(ev)

    ctrl = DebugController(on_event=on_event)

    with patch("jet.debug.controller.terminal.spawn", side_effect=_make_fake_spawn()):
        await ctrl.start(target=FIXTURE, terminal_template="{cmd}")
        for _ in range(50):
            if ctrl.state == DebugState.EXITED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.EXITED
    await _drain_procs()


@pytest.mark.asyncio
async def test_controller_pauses_on_breakpoint():
    events: list = []

    def on_event(ev):
        events.append(ev)

    ctrl = DebugController(on_event=on_event)
    ctrl.toggle_breakpoint(FIXTURE, 3)

    with patch("jet.debug.controller.terminal.spawn", side_effect=_make_fake_spawn()):
        await ctrl.start(target=FIXTURE, terminal_template="{cmd}")
        for _ in range(50):
            if ctrl.state == DebugState.PAUSED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.PAUSED
        assert ctrl.current_paused is not None
        assert ctrl.current_paused.line == 3

        await ctrl.continue_()
        for _ in range(50):
            if ctrl.state == DebugState.EXITED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.EXITED

    await _drain_procs()
