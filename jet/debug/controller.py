"""DebugController — owns the debug socket server, state, breakpoints."""

from __future__ import annotations

import asyncio
import enum
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Callable

import jet.debug.terminal as terminal
from jet.debug.protocol import (
    Continue, Exception_, Exited, Message, Paused, Ready, SetBreakpoints,
    StepInto, StepOut, StepOver, Stop, decode, encode,
)


class DebugState(str, enum.Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    EXITED = "exited"
    ERROR = "error"


class DebugController:
    """Async controller; lives inside the Textual event loop."""

    def __init__(self, on_event: Callable[[Message], None]) -> None:
        self._on_event = on_event
        self.state: DebugState = DebugState.IDLE
        self.breakpoints: dict[Path, set[int]] = {}
        self.current_paused: Paused | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._server: asyncio.base_events.Server | None = None
        self._sock_path: str | None = None
        self._temp_file: Path | None = None
        self._target: Path | None = None
        self._read_task: asyncio.Task | None = None
        self._error: str | None = None

    # ------------------------------------------------------------ public API

    def toggle_breakpoint(self, file: Path, line: int) -> bool:
        s = self.breakpoints.setdefault(file.resolve(), set())
        if line in s:
            s.remove(line)
            on = False
        else:
            s.add(line)
            on = True
        if self.state in (DebugState.RUNNING, DebugState.PAUSED) and self._writer is not None:
            self._send(SetBreakpoints(file=str(file.resolve()), lines=sorted(s)))
        return on

    def get_breakpoints(self, file: Path) -> set[int]:
        return set(self.breakpoints.get(file.resolve(), set()))

    async def start(
        self,
        *,
        target: Path,
        buffer_text: str | None = None,
        terminal_template: str = (
            'osascript -e \'tell application "LiquidTerminal" to do script "{cmd}"\''
        ),
    ) -> None:
        if self.state not in (DebugState.IDLE, DebugState.EXITED, DebugState.ERROR):
            raise RuntimeError(f"cannot start while state={self.state}")
        self.state = DebugState.STARTING
        self.current_paused = None
        self._error = None

        # Resolve target / temp file.
        if buffer_text is not None:
            tf = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8")
            tf.write(buffer_text)
            tf.close()
            self._temp_file = Path(tf.name)
            self._target = self._temp_file
        else:
            self._temp_file = None
            self._target = target.resolve()

        # Socket path.
        self._sock_path = os.path.join(tempfile.gettempdir(), f"jet-debug-{uuid.uuid4().hex}.sock")
        conn_fut: asyncio.Future = asyncio.get_event_loop().create_future()

        async def on_conn(reader, writer):
            if not conn_fut.done():
                conn_fut.set_result((reader, writer))

        self._server = await asyncio.start_unix_server(on_conn, path=self._sock_path)

        # Spawn external terminal running the runner.
        argv = [sys.executable, "-m", "jet.debug.runner", str(self._target), self._sock_path]
        try:
            terminal.spawn(terminal_template, argv)
        except terminal.TerminalSpawnError as e:
            self._error = str(e)
            self.state = DebugState.ERROR
            await self._cleanup()
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(conn_fut, timeout=5.0)
        except asyncio.TimeoutError:
            self._error = "Runner did not connect within 5 s"
            self.state = DebugState.ERROR
            await self._cleanup()
            return

        # Read Ready, send BPs and Continue.
        assert self._reader is not None
        first = decode(await self._reader.readline())
        assert isinstance(first, Ready)

        for f, lines in self.breakpoints.items():
            self._send(SetBreakpoints(file=str(f), lines=sorted(lines)))
        if not self.breakpoints:
            self._send(SetBreakpoints(file=str(self._target), lines=[]))
        self._send(Continue())
        self.state = DebugState.RUNNING

        self._read_task = asyncio.create_task(self._read_loop())

    async def continue_(self) -> None:
        self._send_step(Continue())

    async def step_over(self) -> None:
        self._send_step(StepOver())

    async def step_into(self) -> None:
        self._send_step(StepInto())

    async def step_out(self) -> None:
        self._send_step(StepOut())

    async def stop(self) -> None:
        if self._writer is None:
            return
        self._send(Stop())
        # Give it 1 s to send Exited; otherwise force cleanup.
        try:
            await asyncio.wait_for(self._await_exited(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        await self._cleanup()

    # ------------------------------------------------------------ internals

    def _send(self, msg: Message) -> None:
        if self._writer is None:
            return
        self._writer.write(encode(msg))

    def _send_step(self, msg: Message) -> None:
        if self.state != DebugState.PAUSED:
            return
        self._send(msg)
        self.state = DebugState.RUNNING
        self.current_paused = None
        self._on_event(msg)  # let UI clear the highlight

    async def _await_exited(self) -> None:
        while self.state not in (DebugState.EXITED, DebugState.ERROR, DebugState.IDLE):
            await asyncio.sleep(0.05)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    # EOF without Exited → treat as crash.
                    if self.state != DebugState.EXITED:
                        self._on_event(Exited(code=-1))
                        self.state = DebugState.EXITED
                    return
                msg = decode(line)
                if isinstance(msg, Paused):
                    self.current_paused = msg
                    self.state = DebugState.PAUSED
                    self._on_event(msg)
                elif isinstance(msg, Exception_):
                    self._on_event(msg)
                elif isinstance(msg, Exited):
                    self.state = DebugState.EXITED
                    self.current_paused = None
                    self._on_event(msg)
                    return
                else:
                    self._on_event(msg)
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        if self._sock_path and os.path.exists(self._sock_path):
            try:
                os.unlink(self._sock_path)
            except OSError:
                pass
        self._sock_path = None
        if self._temp_file is not None and self._temp_file.exists():
            try:
                self._temp_file.unlink()
            except OSError:
                pass
        self._temp_file = None
