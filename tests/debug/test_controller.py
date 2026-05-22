import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jet.debug.controller import DebugController, DebugState


FIXTURE = Path(__file__).parent / "fixtures" / "simple.py"


@pytest.mark.asyncio
async def test_controller_start_runs_through_to_exited():
    """End-to-end with the real runner — terminal spawn replaced by raw subprocess."""
    events: list = []

    def on_event(ev):
        events.append(ev)

    ctrl = DebugController(on_event=on_event)

    # Replace terminal.spawn to invoke the runner directly (no real terminal).
    def fake_spawn(template, argv):
        asyncio.get_event_loop()._fake_proc = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        )

    with patch("jet.debug.controller.terminal.spawn", side_effect=fake_spawn):
        await ctrl.start(target=FIXTURE, terminal_template="{cmd}")
        # Wait for exited.
        for _ in range(50):
            if ctrl.state == DebugState.EXITED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.EXITED
    # Cleanup background task
    proc_task = getattr(asyncio.get_event_loop(), "_fake_proc", None)
    if proc_task:
        proc = await proc_task
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()


@pytest.mark.asyncio
async def test_controller_pauses_on_breakpoint():
    events: list = []

    def on_event(ev):
        events.append(ev)

    ctrl = DebugController(on_event=on_event)
    ctrl.toggle_breakpoint(FIXTURE, 3)

    def fake_spawn(template, argv):
        asyncio.get_event_loop()._fake_proc = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        )

    with patch("jet.debug.controller.terminal.spawn", side_effect=fake_spawn):
        await ctrl.start(target=FIXTURE, terminal_template="{cmd}")
        # Wait for paused.
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

    proc_task = getattr(asyncio.get_event_loop(), "_fake_proc", None)
    if proc_task:
        proc = await proc_task
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
