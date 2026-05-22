import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from jet.debug.controller import DebugController, DebugState
from jet.debug.protocol import Paused


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
async def test_full_session_paused_then_continued():
    events: list = []
    ctrl = DebugController(on_event=lambda ev: events.append(ev))
    ctrl.toggle_breakpoint(FIXTURE, 3)

    with patch("jet.debug.controller.terminal.spawn", side_effect=_make_fake_spawn()):
        await ctrl.start(target=FIXTURE, terminal_template="{cmd}")
        for _ in range(50):
            if ctrl.state == DebugState.PAUSED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.PAUSED
        paused = [e for e in events if isinstance(e, Paused)]
        assert paused and paused[0].line == 3

        await ctrl.continue_()
        for _ in range(50):
            if ctrl.state == DebugState.EXITED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.EXITED
    await _drain_procs()
