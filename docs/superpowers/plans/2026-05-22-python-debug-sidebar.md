# Python Debug Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Python debug sidebar to the `jet` TUI editor that runs the active file under bdb, supports breakpoints + step over/into/out + continue + stop, shows locals and globals in a sidebar, highlights the current execution line in the editor gutter, and routes program stdio to an external terminal so `input()` works.

**Architecture:** Two-process model. The editor (parent) launches the user's external terminal app (default LiquidTerminal.app via `osascript`); that terminal runs `python -m jet.debug.runner <target> <socket_path>`. Runner inherits the terminal's tty for stdin/stdout/stderr. A separate UNIX domain socket carries JSON-lines control messages (set_breakpoints, continue, step_*, stop) and event messages (ready, paused with locals/globals/stack, exception, exited) between editor and runner. The runner uses a `bdb.Bdb` subclass; the editor exposes a `DebugPanel` Textual widget added as the third sidebar in the existing `tree → settings → debug` cycle.

**Tech Stack:** Python 3.11, Textual ≥ 0.85 (already in deps), `bdb` + `runpy` + `asyncio` + `reprlib` from stdlib. `pytest` + `pytest-asyncio` (already dev deps).

**Note about VCS:** This project is not a git repository. The plan therefore replaces "git commit" steps with **Checkpoint** markers (a paragraph stating what should be working at that point). If `git init` has been run by the time the plan is executed, treat each Checkpoint as a real `git commit` with the suggested message.

---

## File Structure

Files created or modified:

```
jet/
  app.py                          # MODIFY: add sidebar-debug to cycle, hook controller
  editor.py                       # MODIFY: breakpoints, current_exec_line, gutter, click
  settings_panel.py               # MODIFY: debug_terminal_command field + Input
  debug/
    __init__.py                   # CREATE
    protocol.py                   # CREATE: dataclasses + JSON codec
    runner.py                     # CREATE: bdb subclass + entrypoint
    terminal.py                   # CREATE: spawn external terminal
    controller.py                 # CREATE: lifecycle + socket + state
    panel.py                      # CREATE: DebugPanel widget
tests/
  debug/
    __init__.py                   # CREATE
    fixtures/
      simple.py                   # CREATE: tiny target script
      raises.py                   # CREATE: target that raises
    test_protocol.py              # CREATE
    test_runner_basic.py          # CREATE: ready/bp/continue/exited
    test_runner_paused.py         # CREATE: locals/globals/stack
    test_runner_step.py           # CREATE: step over/into/out
    test_runner_exception.py      # CREATE
    test_terminal.py              # CREATE
    test_controller.py            # CREATE
    test_panel.py                 # CREATE
    test_editor_gutter.py         # CREATE
    test_settings_panel_debug.py  # CREATE
```

Responsibilities (one purpose per file):
- `protocol.py` — message types + serialization, no I/O.
- `runner.py` — bdb subclass, socket client, target execution. Runs in the external terminal's process.
- `terminal.py` — single function: spawn external terminal with a command template.
- `controller.py` — owns socket server, state machine, breakpoint map. Async, runs inside the Textual app.
- `panel.py` — pure UI widget; reads controller state, calls controller methods on button presses.
- `editor.py` (delta) — gutter markers + Option+click handling.

---

## Task 1: Module skeleton + dependencies sanity check

**Files:**
- Create: `jet/debug/__init__.py`
- Create: `tests/debug/__init__.py`
- Create: `tests/debug/fixtures/simple.py`
- Create: `tests/debug/fixtures/raises.py`

- [ ] **Step 1: Create empty package files**

`jet/debug/__init__.py`:
```python
"""jet.debug — Python debugger backend + sidebar UI."""
```

`tests/debug/__init__.py`:
```python
```

- [ ] **Step 2: Create fixture scripts**

`tests/debug/fixtures/simple.py`:
```python
x = 1
y = 2
z = x + y
print(z)
```

`tests/debug/fixtures/raises.py`:
```python
a = 10
b = 0
c = a / b
```

- [ ] **Step 3: Verify pytest-asyncio is configured**

Run: `uv run pytest --collect-only tests/debug 2>&1 | head -20`
Expected: `no tests collected` (no test files yet), no errors.

- [ ] **Step 4: Add pytest-asyncio mode to pyproject if missing**

Open `pyproject.toml`. If there is no `[tool.pytest.ini_options]` block, add:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 5: Checkpoint**

Working: package directories created; pytest discovers them. Suggested message: `feat(debug): scaffold jet.debug package`.

---

## Task 2: Protocol dataclasses + codec

**Files:**
- Create: `jet/debug/protocol.py`
- Test: `tests/debug/test_protocol.py`

- [ ] **Step 1: Write failing tests**

`tests/debug/test_protocol.py`:
```python
from jet.debug.protocol import (
    Ready, Paused, Exited, Exception_, SetBreakpoints,
    Continue, StepOver, StepInto, StepOut, Stop,
    encode, decode,
)


def test_roundtrip_ready():
    msg = Ready()
    assert decode(encode(msg)) == msg


def test_roundtrip_set_breakpoints():
    msg = SetBreakpoints(file="/tmp/foo.py", lines=[1, 2, 3])
    assert decode(encode(msg)) == msg


def test_roundtrip_continue():
    assert decode(encode(Continue())) == Continue()


def test_roundtrip_step_variants():
    for cls in (StepOver, StepInto, StepOut, Stop):
        assert decode(encode(cls())) == cls()


def test_roundtrip_paused_with_unicode_and_large_repr():
    big = "x" * 500
    msg = Paused(
        file="/tmp/foo.py",
        line=42,
        locals={"name": "'héllo'", "long": big},
        globals={"__name__": "'__main__'"},
        stack=[{"file": "/tmp/foo.py", "line": 42, "func": "main"}],
    )
    assert decode(encode(msg)) == msg


def test_roundtrip_exception():
    msg = Exception_(
        file="/tmp/foo.py",
        line=3,
        exc_type="ZeroDivisionError",
        exc_value="division by zero",
        traceback="Traceback (most recent call last):\n  ...",
    )
    assert decode(encode(msg)) == msg


def test_roundtrip_exited():
    assert decode(encode(Exited(code=0))) == Exited(code=0)
    assert decode(encode(Exited(code=-1))) == Exited(code=-1)


def test_encode_appends_newline():
    out = encode(Ready())
    assert out.endswith(b"\n")
    assert b"\n" not in out[:-1]


def test_decode_rejects_unknown_type():
    import pytest
    with pytest.raises(ValueError):
        decode(b'{"type": "garbage"}\n')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/debug/test_protocol.py -v`
Expected: `ModuleNotFoundError: No module named 'jet.debug.protocol'`.

- [ ] **Step 3: Implement protocol**

`jet/debug/protocol.py`:
```python
"""JSON-lines wire protocol for the jet debugger.

Pure data + (de)serialization. No I/O.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class Ready:
    type: str = "ready"


@dataclass(frozen=True)
class Paused:
    file: str
    line: int
    locals: dict[str, str]
    globals: dict[str, str]
    stack: list[dict[str, Any]]
    type: str = "paused"


@dataclass(frozen=True)
class Exception_:
    file: str
    line: int
    exc_type: str
    exc_value: str
    traceback: str
    type: str = "exception"


@dataclass(frozen=True)
class Exited:
    code: int
    type: str = "exited"


@dataclass(frozen=True)
class SetBreakpoints:
    file: str
    lines: list[int]
    type: str = "set_breakpoints"


@dataclass(frozen=True)
class Continue:
    type: str = "continue"


@dataclass(frozen=True)
class StepOver:
    type: str = "step_over"


@dataclass(frozen=True)
class StepInto:
    type: str = "step_into"


@dataclass(frozen=True)
class StepOut:
    type: str = "step_out"


@dataclass(frozen=True)
class Stop:
    type: str = "stop"


Message = Union[
    Ready, Paused, Exception_, Exited,
    SetBreakpoints, Continue, StepOver, StepInto, StepOut, Stop,
]


_BY_TYPE: dict[str, type] = {
    cls().type if cls in (Ready, Continue, StepOver, StepInto, StepOut, Stop) else cls.__dataclass_fields__["type"].default: cls  # type: ignore[misc]
    for cls in (
        Ready, Paused, Exception_, Exited,
        SetBreakpoints, Continue, StepOver, StepInto, StepOut, Stop,
    )
}


def encode(msg: Message) -> bytes:
    return (json.dumps(asdict(msg), ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes) -> Message:
    data = json.loads(line.decode("utf-8"))
    t = data.get("type")
    cls = _BY_TYPE.get(t)
    if cls is None:
        raise ValueError(f"Unknown message type: {t!r}")
    payload = {k: v for k, v in data.items() if k != "type"}
    return cls(**payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/debug/test_protocol.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 5: Checkpoint**

Working: protocol round-trips every message type. Suggested message: `feat(debug): protocol dataclasses + JSON codec`.

---

## Task 3: Runner — handshake, breakpoints, continue, exited

**Files:**
- Create: `jet/debug/runner.py`
- Test: `tests/debug/test_runner_basic.py`

- [ ] **Step 1: Write failing tests**

`tests/debug/test_runner_basic.py`:
```python
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from jet.debug.protocol import (
    Continue, Exited, Ready, SetBreakpoints, decode, encode,
)


FIXTURE = Path(__file__).parent / "fixtures" / "simple.py"


async def _accept_one(sock_path: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    fut: asyncio.Future = asyncio.get_event_loop().create_future()

    async def cb(r, w):
        if not fut.done():
            fut.set_result((r, w))

    server = await asyncio.start_unix_server(cb, path=sock_path)
    return server, fut


@pytest.mark.asyncio
async def test_runner_ready_and_exited():
    with tempfile.TemporaryDirectory() as td:
        sock = os.path.join(td, "dbg.sock")
        server, fut = await _accept_one(sock)

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "jet.debug.runner", str(FIXTURE), sock,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        reader, writer = await asyncio.wait_for(fut, timeout=5)
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=2)
            assert decode(line) == Ready()

            writer.write(encode(SetBreakpoints(file=str(FIXTURE), lines=[])))
            writer.write(encode(Continue()))
            await writer.drain()

            # Should exit cleanly (no breakpoints set).
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            assert decode(line) == Exited(code=0)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            server.close()
            await server.wait_closed()
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()


@pytest.mark.asyncio
async def test_runner_stops_at_breakpoint():
    with tempfile.TemporaryDirectory() as td:
        sock = os.path.join(td, "dbg.sock")
        server, fut = await _accept_one(sock)

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "jet.debug.runner", str(FIXTURE), sock,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        reader, writer = await asyncio.wait_for(fut, timeout=5)
        try:
            assert decode(await asyncio.wait_for(reader.readline(), 2)) == Ready()

            writer.write(encode(SetBreakpoints(file=str(FIXTURE), lines=[3])))
            writer.write(encode(Continue()))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), 5)
            msg = decode(line)
            assert msg.type == "paused"
            assert msg.line == 3
            assert msg.file.endswith("simple.py")

            from jet.debug.protocol import Continue as Cont
            writer.write(encode(Cont()))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), 5)
            assert decode(line) == Exited(code=0)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            server.close()
            await server.wait_closed()
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/debug/test_runner_basic.py -v`
Expected: `ModuleNotFoundError: No module named 'jet.debug.runner'`.

- [ ] **Step 3: Implement runner — minimal**

`jet/debug/runner.py`:
```python
"""jet.debug.runner — child process running user code under bdb.

Started by an external terminal. Connects back to the editor via a UNIX
socket. Reads commands, emits events. stdin/stdout/stderr are the
external terminal's tty.
"""

from __future__ import annotations

import bdb
import json
import reprlib
import runpy
import socket
import sys
import traceback
import types
from pathlib import Path
from typing import Any

from jet.debug.protocol import (
    Continue, Exception_, Exited, Paused, Ready, SetBreakpoints,
    StepInto, StepOut, StepOver, Stop, decode, encode,
)


_REPR = reprlib.Repr()
_REPR.maxstring = 80
_REPR.maxother = 80
_REPR.maxlist = _REPR.maxtuple = _REPR.maxdict = 6


def _safe_repr(v: Any) -> str:
    try:
        return _REPR.repr(v)
    except Exception as e:
        return f"<repr error: {e}>"


def _filter_globals(g: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    import builtins
    for k, v in g.items():
        if k.startswith("__") and k not in ("__name__", "__file__"):
            continue
        if isinstance(v, types.ModuleType):
            continue
        if isinstance(v, type) and getattr(v, "__module__", None) == "builtins":
            continue
        out[k] = _safe_repr(v)
    return out


class _SockIO:
    """Line-delimited JSON over a connected socket."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = b""

    def send(self, msg) -> None:
        self._sock.sendall(encode(msg))

    def recv(self):
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("editor closed control socket")
            self._buf += chunk
        line, _, rest = self._buf.partition(b"\n")
        self._buf = rest
        return decode(line + b"\n")

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


class JetDebugger(bdb.Bdb):
    def __init__(self, io: _SockIO, target: Path) -> None:
        super().__init__()
        self._io = io
        self._target = str(target.resolve())
        self._step_mode: str | None = None  # "over" | "into" | "out" | None

    # -------- breakpoint management

    def apply_breakpoints(self, file: str, lines: list[int]) -> None:
        # Clear existing for that file then set new.
        for b in list(self.get_file_breaks(file)):
            self.clear_break(file, b)
        for ln in lines:
            self.set_break(file, ln)

    # -------- bdb callbacks

    def user_line(self, frame) -> None:
        # Skip frames not in the target file unless stepping into.
        file = frame.f_code.co_filename
        if file != self._target and self._step_mode != "into":
            # Allow continuing through library code transparently.
            return
        self._pause(frame)

    def user_return(self, frame, return_value) -> None:
        if self._step_mode == "out":
            self._step_mode = None
            self._pause(frame)

    def user_exception(self, frame, exc_info) -> None:
        exc_type, exc_value, tb = exc_info
        payload = Exception_(
            file=frame.f_code.co_filename,
            line=frame.f_lineno,
            exc_type=exc_type.__name__,
            exc_value=str(exc_value),
            traceback="".join(traceback.format_exception(exc_type, exc_value, tb)),
        )
        self._io.send(payload)
        # Continue so the program propagates the exception normally.
        self.set_continue()

    # -------- pause + command loop

    def _pause(self, frame) -> None:
        stack: list[dict[str, Any]] = []
        f = frame
        while f is not None:
            stack.append({
                "file": f.f_code.co_filename,
                "line": f.f_lineno,
                "func": f.f_code.co_name,
            })
            f = f.f_back
        self._io.send(Paused(
            file=frame.f_code.co_filename,
            line=frame.f_lineno,
            locals={k: _safe_repr(v) for k, v in frame.f_locals.items()},
            globals=_filter_globals(frame.f_globals),
            stack=stack,
        ))
        self._await_command(frame)

    def _await_command(self, frame) -> None:
        while True:
            msg = self._io.recv()
            if isinstance(msg, Continue):
                self._step_mode = None
                self.set_continue()
                return
            if isinstance(msg, StepOver):
                self._step_mode = "over"
                self.set_next(frame)
                return
            if isinstance(msg, StepInto):
                self._step_mode = "into"
                self.set_step()
                return
            if isinstance(msg, StepOut):
                self._step_mode = "out"
                self.set_return(frame)
                return
            if isinstance(msg, Stop):
                raise SystemExit(0)
            if isinstance(msg, SetBreakpoints):
                self.apply_breakpoints(msg.file, msg.lines)
                # Loop again for the next command.
                continue
            # Unknown — ignore.


def _connect(sock_path: str) -> _SockIO:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    return _SockIO(s)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m jet.debug.runner <target> <socket>", file=sys.stderr)
        return 2
    target = Path(argv[1])
    sock_path = argv[2]

    io = _connect(sock_path)
    try:
        io.send(Ready())
        # First command after Ready must be SetBreakpoints (possibly empty)
        # followed by Continue.
        first = io.recv()
        if isinstance(first, SetBreakpoints):
            pass  # applied below via debugger
        elif isinstance(first, Stop):
            io.send(Exited(code=0))
            return 0
        else:
            # Tolerate other orderings.
            pass

        dbg = JetDebugger(io, target)
        if isinstance(first, SetBreakpoints):
            dbg.apply_breakpoints(first.file, first.lines)

        # Expect Continue (or step) to start execution.
        start = io.recv()
        if isinstance(start, SetBreakpoints):
            dbg.apply_breakpoints(start.file, start.lines)
            start = io.recv()
        if isinstance(start, Stop):
            io.send(Exited(code=0))
            return 0

        code = 0
        try:
            dbg.run(
                compile(target.read_text(encoding="utf-8"), str(target), "exec"),
                globals={"__name__": "__main__", "__file__": str(target)},
            )
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else (0 if e.code in (None, "") else 1)
        except BaseException:
            traceback.print_exc()
            code = 1

        io.send(Exited(code=code))
    finally:
        try:
            input("\n[Debug session ended — press Enter to close]")
        except (EOFError, KeyboardInterrupt):
            pass
        io.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/debug/test_runner_basic.py -v -s`
Expected: both tests PASS. (Tests pipe DEVNULL into the runner's stdin, so the trailing `input()` returns immediately with EOFError, which is caught.)

- [ ] **Step 5: Checkpoint**

Working: runner spawns, hand-shakes, hits a breakpoint at the right line, continues to end, exits 0. Suggested message: `feat(debug): runner handshake + breakpoints + continue`.

---

## Task 4: Runner — locals/globals/stack on pause

**Files:**
- Test: `tests/debug/test_runner_paused.py`
- (Runner already emits this; this task only adds coverage.)

- [ ] **Step 1: Write tests**

`tests/debug/test_runner_paused.py`:
```python
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from jet.debug.protocol import (
    Continue, Ready, SetBreakpoints, decode, encode,
)


FIXTURE = Path(__file__).parent / "fixtures" / "simple.py"


async def _spawn(sock: str):
    fut = asyncio.get_event_loop().create_future()

    async def cb(r, w):
        if not fut.done():
            fut.set_result((r, w))

    server = await asyncio.start_unix_server(cb, path=sock)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "jet.debug.runner", str(FIXTURE), sock,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    reader, writer = await asyncio.wait_for(fut, 5)
    return server, proc, reader, writer


@pytest.mark.asyncio
async def test_paused_payload_contains_locals_globals_stack():
    with tempfile.TemporaryDirectory() as td:
        sock = os.path.join(td, "d.sock")
        server, proc, reader, writer = await _spawn(sock)
        try:
            assert decode(await asyncio.wait_for(reader.readline(), 2)) == Ready()
            writer.write(encode(SetBreakpoints(file=str(FIXTURE), lines=[3])))
            writer.write(encode(Continue()))
            await writer.drain()

            msg = decode(await asyncio.wait_for(reader.readline(), 5))
            assert msg.type == "paused"
            # By line 3 (z = x + y), x and y exist in globals (module-level).
            assert "x" in msg.globals
            assert "y" in msg.globals
            assert msg.globals["x"] == "1"
            assert msg.globals["y"] == "2"
            # Stack has at least one frame.
            assert len(msg.stack) >= 1
            assert msg.stack[0]["file"].endswith("simple.py")
            assert msg.stack[0]["line"] == 3

            from jet.debug.protocol import Continue as Cont
            writer.write(encode(Cont()))
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            server.close()
            await server.wait_closed()
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/debug/test_runner_paused.py -v`
Expected: PASS.

- [ ] **Step 3: Checkpoint**

Suggested message: `test(debug): paused payload includes locals/globals/stack`.

---

## Task 5: Runner — stepping

**Files:**
- Create: `tests/debug/fixtures/funcs.py`
- Test: `tests/debug/test_runner_step.py`

- [ ] **Step 1: Create fixture**

`tests/debug/fixtures/funcs.py`:
```python
def inner(n):
    return n + 1


def outer():
    a = 1
    b = inner(a)
    return b


outer()
```

- [ ] **Step 2: Write failing tests**

`tests/debug/test_runner_step.py`:
```python
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from jet.debug.protocol import (
    Continue, Ready, SetBreakpoints, StepInto, StepOut, StepOver,
    decode, encode,
)


FIXTURE = Path(__file__).parent / "fixtures" / "funcs.py"


async def _spawn(sock: str, target: Path):
    fut = asyncio.get_event_loop().create_future()

    async def cb(r, w):
        if not fut.done():
            fut.set_result((r, w))

    server = await asyncio.start_unix_server(cb, path=sock)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "jet.debug.runner", str(target), sock,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    reader, writer = await asyncio.wait_for(fut, 5)
    return server, proc, reader, writer


async def _drive(reader, writer, commands_after_pause):
    """Generator helper: hand-shake, set BPs, then alternate pause/command."""
    assert decode(await asyncio.wait_for(reader.readline(), 2)) == Ready()
    yield None


@pytest.mark.asyncio
async def test_step_over_does_not_enter_function():
    with tempfile.TemporaryDirectory() as td:
        sock = os.path.join(td, "d.sock")
        server, proc, reader, writer = await _spawn(sock, FIXTURE)
        try:
            assert decode(await asyncio.wait_for(reader.readline(), 2)) == Ready()
            # Break at line 7 (b = inner(a)).
            writer.write(encode(SetBreakpoints(file=str(FIXTURE), lines=[7])))
            writer.write(encode(Continue()))
            await writer.drain()

            msg = decode(await asyncio.wait_for(reader.readline(), 5))
            assert msg.type == "paused"
            assert msg.line == 7

            writer.write(encode(StepOver()))
            await writer.drain()

            msg = decode(await asyncio.wait_for(reader.readline(), 5))
            assert msg.type == "paused"
            # Step over from line 7 should land on line 8 (return b), still in outer.
            assert msg.line == 8
            assert msg.stack[0]["func"] == "outer"

            writer.write(encode(Continue()))
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            server.close()
            await server.wait_closed()
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()


@pytest.mark.asyncio
async def test_step_into_enters_function():
    with tempfile.TemporaryDirectory() as td:
        sock = os.path.join(td, "d.sock")
        server, proc, reader, writer = await _spawn(sock, FIXTURE)
        try:
            assert decode(await asyncio.wait_for(reader.readline(), 2)) == Ready()
            writer.write(encode(SetBreakpoints(file=str(FIXTURE), lines=[7])))
            writer.write(encode(Continue()))
            await writer.drain()

            msg = decode(await asyncio.wait_for(reader.readline(), 5))
            assert msg.line == 7

            writer.write(encode(StepInto()))
            await writer.drain()

            msg = decode(await asyncio.wait_for(reader.readline(), 5))
            assert msg.type == "paused"
            # Should now be inside inner().
            assert msg.stack[0]["func"] == "inner"
            assert msg.line == 2  # `return n + 1`

            writer.write(encode(Continue()))
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            server.close()
            await server.wait_closed()
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()


@pytest.mark.asyncio
async def test_step_out_returns_to_caller():
    with tempfile.TemporaryDirectory() as td:
        sock = os.path.join(td, "d.sock")
        server, proc, reader, writer = await _spawn(sock, FIXTURE)
        try:
            assert decode(await asyncio.wait_for(reader.readline(), 2)) == Ready()
            # Break inside inner.
            writer.write(encode(SetBreakpoints(file=str(FIXTURE), lines=[2])))
            writer.write(encode(Continue()))
            await writer.drain()

            msg = decode(await asyncio.wait_for(reader.readline(), 5))
            assert msg.stack[0]["func"] == "inner"

            writer.write(encode(StepOut()))
            await writer.drain()

            msg = decode(await asyncio.wait_for(reader.readline(), 5))
            assert msg.type == "paused"
            assert msg.stack[0]["func"] == "outer"

            writer.write(encode(Continue()))
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            server.close()
            await server.wait_closed()
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/debug/test_runner_step.py -v`
Expected: all three PASS. If `step_into` lands somewhere unexpected because of `user_line` filtering, fix the runner: in `user_line`, also allow entering target-module functions when `_step_mode == "into"`. The existing implementation handles this via `set_step()` + the `_step_mode == "into"` bypass in `user_line`.

- [ ] **Step 4: Checkpoint**

Suggested message: `feat(debug): runner step over/into/out`.

---

## Task 6: Runner — exception path

**Files:**
- Test: `tests/debug/test_runner_exception.py`

- [ ] **Step 1: Write test**

`tests/debug/test_runner_exception.py`:
```python
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from jet.debug.protocol import Continue, Ready, SetBreakpoints, decode, encode


FIXTURE = Path(__file__).parent / "fixtures" / "raises.py"


@pytest.mark.asyncio
async def test_runner_emits_exception_then_exited():
    with tempfile.TemporaryDirectory() as td:
        sock = os.path.join(td, "d.sock")
        fut = asyncio.get_event_loop().create_future()

        async def cb(r, w):
            if not fut.done():
                fut.set_result((r, w))

        server = await asyncio.start_unix_server(cb, path=sock)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "jet.debug.runner", str(FIXTURE), sock,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        reader, writer = await asyncio.wait_for(fut, 5)
        try:
            assert decode(await asyncio.wait_for(reader.readline(), 2)) == Ready()
            writer.write(encode(SetBreakpoints(file=str(FIXTURE), lines=[])))
            writer.write(encode(Continue()))
            await writer.drain()

            # Expect an exception event followed by exited.
            seen_exc = False
            seen_exit = False
            for _ in range(5):
                line = await asyncio.wait_for(reader.readline(), 5)
                if not line:
                    break
                msg = decode(line)
                if msg.type == "exception":
                    assert msg.exc_type == "ZeroDivisionError"
                    seen_exc = True
                elif msg.type == "exited":
                    assert msg.code != 0
                    seen_exit = True
                    break
            assert seen_exc and seen_exit
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            server.close()
            await server.wait_closed()
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/debug/test_runner_exception.py -v`
Expected: PASS.

- [ ] **Step 3: Checkpoint**

Suggested message: `feat(debug): runner emits exception event on uncaught error`.

---

## Task 7: External terminal spawner

**Files:**
- Create: `jet/debug/terminal.py`
- Test: `tests/debug/test_terminal.py`

- [ ] **Step 1: Write failing tests**

`tests/debug/test_terminal.py`:
```python
from unittest.mock import patch

import pytest

from jet.debug.terminal import build_command, spawn, TerminalSpawnError


def test_build_command_substitutes_cmd_placeholder():
    template = 'osascript -e \'tell app "X" to do script "{cmd}"\''
    out = build_command(template, ["python", "-m", "jet.debug.runner", "/tmp/foo.py", "/tmp/d.sock"])
    assert "python -m jet.debug.runner /tmp/foo.py /tmp/d.sock" in out


def test_build_command_quotes_args_with_spaces():
    template = "{cmd}"
    out = build_command(template, ["python", "/a path/foo.py"])
    assert "'/a path/foo.py'" in out


def test_spawn_invokes_subprocess_with_shell_true():
    with patch("jet.debug.terminal.subprocess.Popen") as p:
        p.return_value.poll.return_value = None
        spawn("{cmd}", ["python", "/tmp/x.py"])
        p.assert_called_once()
        kwargs = p.call_args.kwargs
        assert kwargs.get("shell") is True


def test_spawn_raises_on_immediate_nonzero_exit():
    with patch("jet.debug.terminal.subprocess.Popen") as p:
        p.return_value.poll.return_value = 1
        p.return_value.communicate.return_value = (b"", b"some error")
        with pytest.raises(TerminalSpawnError):
            spawn("{cmd}", ["python", "/tmp/x.py"])
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/debug/test_terminal.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`jet/debug/terminal.py`:
```python
"""Spawn an external terminal app running a given command."""

from __future__ import annotations

import shlex
import subprocess
import time


class TerminalSpawnError(RuntimeError):
    pass


def build_command(template: str, argv: list[str]) -> str:
    joined = " ".join(shlex.quote(a) for a in argv)
    return template.format(cmd=joined)


def spawn(template: str, argv: list[str]) -> None:
    """Launch the external terminal app with the runner command.

    Raises TerminalSpawnError if the spawn fails immediately.
    """
    cmd = build_command(template, argv)
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as e:
        raise TerminalSpawnError(f"Could not launch terminal: {e}") from e
    # Give osascript ~150ms to fail fast.
    time.sleep(0.15)
    rc = proc.poll()
    if rc not in (None, 0):
        _, err = proc.communicate(timeout=1)
        raise TerminalSpawnError(
            f"Terminal spawn exited {rc}: {err.decode('utf-8', errors='replace').strip()}"
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/debug/test_terminal.py -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint**

Suggested message: `feat(debug): external terminal spawner`.

---

## Task 8: Controller — lifecycle skeleton

**Files:**
- Create: `jet/debug/controller.py`
- Test: `tests/debug/test_controller.py`

- [ ] **Step 1: Write failing tests**

`tests/debug/test_controller.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/debug/test_controller.py -v`
Expected: `ModuleNotFoundError: No module named 'jet.debug.controller'`.

- [ ] **Step 3: Implement controller**

`jet/debug/controller.py`:
```python
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

from jet.debug import terminal
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/debug/test_controller.py -v`
Expected: both PASS.

- [ ] **Step 5: Checkpoint**

Suggested message: `feat(debug): DebugController lifecycle + state machine`.

---

## Task 9: Controller — stop + crash detection

**Files:**
- Test: `tests/debug/test_controller.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/debug/test_controller.py`:
```python
@pytest.mark.asyncio
async def test_controller_stop_terminates_session():
    ctrl = DebugController(on_event=lambda ev: None)
    ctrl.toggle_breakpoint(FIXTURE, 3)

    def fake_spawn(template, argv):
        asyncio.get_event_loop()._fake_proc2 = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        )

    with patch("jet.debug.controller.terminal.spawn", side_effect=fake_spawn):
        await ctrl.start(target=FIXTURE, terminal_template="{cmd}")
        for _ in range(50):
            if ctrl.state == DebugState.PAUSED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.PAUSED

        await ctrl.stop()
        assert ctrl.state in (DebugState.EXITED, DebugState.IDLE)

    proc_task = getattr(asyncio.get_event_loop(), "_fake_proc2", None)
    if proc_task:
        proc = await proc_task
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/debug/test_controller.py::test_controller_stop_terminates_session -v`
Expected: PASS.

- [ ] **Step 3: Checkpoint**

Suggested message: `test(debug): controller stop transitions to exited`.

---

## Task 10: EditorConfig — debug_terminal_command field

**Files:**
- Modify: `jet/settings_panel.py`
- Test: `tests/debug/test_settings_panel_debug.py`

- [ ] **Step 1: Write failing tests**

`tests/debug/test_settings_panel_debug.py`:
```python
from jet.settings_panel import EditorConfig


def test_editor_config_has_default_debug_terminal_command():
    cfg = EditorConfig()
    assert "{cmd}" in cfg.debug_terminal_command
    assert "LiquidTerminal" in cfg.debug_terminal_command
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/debug/test_settings_panel_debug.py -v`
Expected: `AttributeError: 'EditorConfig' object has no attribute 'debug_terminal_command'`.

- [ ] **Step 3: Add field**

Edit `jet/settings_panel.py`, in the `EditorConfig` dataclass add:

```python
    debug_terminal_command: str = (
        'osascript -e \'tell application "LiquidTerminal" to do script "{cmd}"\''
    )
```

- [ ] **Step 4: Add Input widget to SettingsPanel.compose**

Add to imports:
```python
from textual.widgets import Input, Label, Select, Static, Switch
```

In `compose()`, after the Soft wrap switch, append:
```python
            yield Label("Debug terminal command")
            yield Input(
                value=self._config.debug_terminal_command,
                id="inp-debug-cmd",
                placeholder='osascript -e \'tell application "X" to do script "{cmd}"\'',
            )
```

Add handler:
```python
    @on(Input.Changed, "#inp-debug-cmd")
    def _on_debug_cmd(self, e: Input.Changed) -> None:
        self._config = replace(self._config, debug_terminal_command=e.value)
        self.post_message(self.ConfigChanged(self._config))
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/debug/test_settings_panel_debug.py tests/test_app.py -v`
Expected: PASS. (Existing app test must still pass — verifies settings panel didn't break.)

- [ ] **Step 6: Checkpoint**

Suggested message: `feat(settings): debug_terminal_command field + input`.

---

## Task 11: Editor — breakpoint + current-line state

**Files:**
- Modify: `jet/editor.py`
- Test: `tests/debug/test_editor_gutter.py`

- [ ] **Step 1: Write failing tests**

`tests/debug/test_editor_gutter.py`:
```python
from jet.editor import JetEditor


def test_editor_starts_with_empty_breakpoints():
    ed = JetEditor(text="a=1\nb=2\n")
    assert ed.breakpoints == frozenset()
    assert ed.current_exec_line is None


def test_editor_set_breakpoints():
    ed = JetEditor(text="a=1\nb=2\n")
    ed.set_breakpoints({1, 3})
    assert ed.breakpoints == frozenset({1, 3})


def test_editor_set_current_exec_line():
    ed = JetEditor(text="a=1\nb=2\n")
    ed.set_current_exec_line(2)
    assert ed.current_exec_line == 2
    ed.set_current_exec_line(None)
    assert ed.current_exec_line is None


def test_editor_read_only_toggle():
    ed = JetEditor(text="a=1\n")
    assert ed.read_only is False
    ed.read_only = True
    assert ed.read_only is True
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/debug/test_editor_gutter.py -v`
Expected: `AttributeError: 'JetEditor' object has no attribute 'breakpoints'`.

- [ ] **Step 3: Add state to JetEditor**

Edit `jet/editor.py`. In `JetEditor.__init__`, after `self._use_tabs = cfg.use_tabs`, add:

```python
        self._breakpoints: frozenset[int] = frozenset()
        self._current_exec_line: int | None = None
```

Add properties + setters:
```python
    @property
    def breakpoints(self) -> frozenset[int]:
        return self._breakpoints

    def set_breakpoints(self, lines: set[int] | frozenset[int]) -> None:
        self._breakpoints = frozenset(lines)
        self.refresh()

    @property
    def current_exec_line(self) -> int | None:
        return self._current_exec_line

    def set_current_exec_line(self, line: int | None) -> None:
        self._current_exec_line = line
        if line is not None:
            self.scroll_cursor_visible(center=True)
        self.refresh()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/debug/test_editor_gutter.py -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint**

Suggested message: `feat(editor): breakpoint + current-line state`.

---

## Task 12: Editor — gutter rendering

**Files:**
- Modify: `jet/editor.py`
- Test: `tests/debug/test_editor_gutter.py` (append)

- [ ] **Step 1: Append failing test**

Append:
```python
def test_gutter_breakpoint_marker_present_without_line_numbers():
    from jet.settings_panel import EditorConfig
    cfg = EditorConfig(show_line_numbers=False)
    ed = JetEditor(text="a=1\nb=2\n", config=cfg)
    ed.set_breakpoints({1})
    marker = ed.gutter_marker_for_line(1)
    assert marker is not None
    assert "●" in marker.plain


def test_gutter_current_line_marker():
    from jet.settings_panel import EditorConfig
    cfg = EditorConfig(show_line_numbers=False)
    ed = JetEditor(text="a=1\nb=2\n", config=cfg)
    ed.set_current_exec_line(2)
    marker = ed.gutter_marker_for_line(2)
    assert marker is not None
    assert "▶" in marker.plain


def test_gutter_returns_none_for_unmarked_line():
    ed = JetEditor(text="a=1\nb=2\n")
    assert ed.gutter_marker_for_line(99) is None
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/debug/test_editor_gutter.py -v`
Expected: `AttributeError: 'JetEditor' has no attribute 'gutter_marker_for_line'`.

- [ ] **Step 3: Implement gutter_marker_for_line**

Edit `jet/editor.py`. Add at top:
```python
from rich.text import Text
```

Add method to `JetEditor`:
```python
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
```

To actually paint the gutter, override `_render_line_strip` (Textual TextArea internal hook). Add to `JetEditor`:
```python
    def render_line(self, y):  # type: ignore[override]
        strip = super().render_line(y)
        # Compute the line number in the document.
        try:
            line_index = self.scroll_offset.y + y
        except Exception:
            return strip
        marker = self.gutter_marker_for_line(line_index + 1)
        if marker is None:
            return strip
        # Replace the first cell of the strip with our marker.
        from textual.strip import Strip
        from rich.segment import Segment
        segs = list(strip)
        if not segs:
            return strip
        # Strip's first segment is the gutter — overwrite first char.
        first = segs[0]
        if first.text:
            new_first = Segment(marker.plain + first.text[len(marker.plain):], first.style)
            segs[0] = new_first
        return Strip(segs, strip.cell_length)
```

NOTE: Textual's exact gutter API depends on the version. If `render_line` overriding causes layout issues with line numbers, fall back to drawing the marker into a custom one-cell prefix by enabling a tiny custom margin. If problems arise here, switch implementation to override `_render_line_gutter` instead and re-test. The unit tests above only exercise `gutter_marker_for_line` so they keep passing regardless of which renderer hook is used.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/debug/test_editor_gutter.py -v`
Expected: all PASS.

- [ ] **Step 5: Manual smoke check**

Run: `uv run python -m jet jet/editor.py`
Action: open the editor; nothing crashes; existing tests still pass.
Run: `uv run pytest tests -v`
Expected: full suite PASS.

- [ ] **Step 6: Checkpoint**

Suggested message: `feat(editor): gutter markers for breakpoints + current line`.

---

## Task 13: Editor — Option+click toggles breakpoint

**Files:**
- Modify: `jet/editor.py`
- Test: `tests/debug/test_editor_gutter.py` (append)

- [ ] **Step 1: Append failing test**

```python
def test_option_click_callback_invokes_handler():
    from unittest.mock import Mock
    ed = JetEditor(text="a=1\nb=2\nc=3\n")
    handler = Mock()
    ed.on_breakpoint_toggle_request = handler  # type: ignore[attr-defined]

    # Simulate an option+click via the editor's toggle method.
    ed.request_breakpoint_toggle(line_1based=2)
    handler.assert_called_once_with(2)
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/debug/test_editor_gutter.py::test_option_click_callback_invokes_handler -v`
Expected: `AttributeError: 'JetEditor' has no attribute 'request_breakpoint_toggle'`.

- [ ] **Step 3: Implement**

Edit `jet/editor.py`. Add to imports:
```python
from textual.message import Message
```

Add inside `JetEditor`:
```python
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
```

(Add `from typing import Any` if not already imported.)

Hook the click. Override `_on_click` in `JetEditor`:
```python
    def _on_click(self, event) -> None:  # type: ignore[override]
        # On macOS terminals, Option is usually surfaced as event.meta.
        # Fallback: shift-click also toggles BP when debug sidebar is active.
        meta = getattr(event, "meta", False) or getattr(event, "alt", False)
        if meta:
            # Translate click y to a 1-based line number.
            try:
                line0, _ = self.get_target_document_location(event)
            except Exception:
                super()._on_click(event)
                return
            self.request_breakpoint_toggle(line0 + 1)
            event.stop()
            return
        super()._on_click(event)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/debug/test_editor_gutter.py -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint**

Suggested message: `feat(editor): Option+click requests breakpoint toggle`.

---

## Task 14: DebugPanel widget

**Files:**
- Create: `jet/debug/panel.py`
- Test: `tests/debug/test_panel.py`

- [ ] **Step 1: Write failing tests**

`tests/debug/test_panel.py`:
```python
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
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/debug/test_panel.py -v`
Expected: `ModuleNotFoundError: No module named 'jet.debug.panel'`.

- [ ] **Step 3: Implement**

`jet/debug/panel.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/debug/test_panel.py -v`
Expected: PASS.

- [ ] **Step 5: Checkpoint**

Suggested message: `feat(debug): DebugPanel sidebar widget`.

---

## Task 15: Wire DebugPanel into the App

**Files:**
- Modify: `jet/app.py`
- Modify: `jet/styles.tcss` (only if needed for the new id; otherwise skip)
- Test: `tests/test_app.py` (append)

- [ ] **Step 1: Append failing test**

`tests/test_app.py` append:
```python
import pytest

@pytest.mark.asyncio
async def test_sidebar_cycle_includes_debug(tmp_path):
    from jet.app import JetApp
    f = tmp_path / "x.py"
    f.write_text("a=1\n")
    app = JetApp([f])
    async with app.run_test() as pilot:
        # Cycle once: tree -> settings -> debug
        await pilot.press("ctrl+b")
        await pilot.press("ctrl+b")
        assert app.query_one("#sidebar-debug").display is True
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_app.py::test_sidebar_cycle_includes_debug -v`
Expected: `NoMatches: No nodes match #sidebar-debug`.

- [ ] **Step 3: Modify app.py**

In `jet/app.py`:

a) Add imports near the top:
```python
from .debug.controller import DebugController, DebugState
from .debug.panel import DebugPanel
from .debug.protocol import Exception_, Exited, Paused
```

b) In `__init__`, after `self._active_sidebar: str = "tree"`, replace nothing — add:
```python
        self.debug_controller = DebugController(on_event=self._on_debug_event)
```

c) In `compose()`, after `yield SettingsPanel(...)`, add:
```python
            yield DebugPanel(self.debug_controller, id="sidebar-debug")
```

d) In `on_mount`, after `self.query_one("#sidebar-settings").display = False`, add:
```python
        self.query_one("#sidebar-debug").display = False
```

e) Replace `action_cycle_sidebars` body with a 3-state cycle:
```python
    def action_cycle_sidebars(self) -> None:
        order = ["tree", "settings", "debug"]
        ids = {"tree": "#sidebar-tree", "settings": "#sidebar-settings", "debug": "#sidebar-debug"}
        cur = self._active_sidebar
        # If current is hidden, just show it again instead of cycling.
        cur_w = self.query_one(ids[cur])
        if not cur_w.display:
            cur_w.display = True
            return
        cur_w.display = False
        nxt = order[(order.index(cur) + 1) % len(order)]
        self.query_one(ids[nxt]).display = True
        self._active_sidebar = nxt
```

f) Update `action_toggle_sidebar`:
```python
    def action_toggle_sidebar(self) -> None:
        sid = {"tree": "#sidebar-tree", "settings": "#sidebar-settings", "debug": "#sidebar-debug"}[
            self._active_sidebar
        ]
        w = self.query_one(sid)
        w.display = not w.display
```

g) Wire the debug panel callbacks. In `on_mount`, after the display lines, add:
```python
        panel = self.query_one(DebugPanel)
        panel.on_run_requested = self._debug_run
        panel.on_stop_requested = self.debug_controller.stop
```

h) Add the run handler and event sink to `JetApp`:
```python
    async def _debug_run(self) -> None:
        ed = self._active_editor()
        if ed is None:
            self.notify("No active editor", severity="warning")
            return
        # Only Python files for now.
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
```

i) Wire breakpoint toggle from editor → controller. Inside `open_file` and `new_buffer`, right after creating the editor, add:
```python
        editor.on_breakpoint_toggle_request = lambda line, e=editor: self._toggle_bp(e, line)
```

Add method:
```python
    def _toggle_bp(self, editor, line: int) -> None:
        if editor.path is None:
            self.notify("Save the buffer before setting breakpoints", severity="warning")
            return
        self.debug_controller.toggle_breakpoint(editor.path, line)
        editor.set_breakpoints(self.debug_controller.get_breakpoints(editor.path))
        panel = self.query_one(DebugPanel)
        panel.refresh_breakpoints(self.debug_controller.breakpoints)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests -v`
Expected: full suite PASS. The new sidebar cycle test passes; existing tests untouched.

- [ ] **Step 5: Manual smoke check**

Run: `uv run python -m jet tests/debug/fixtures/simple.py`
Action:
1. Cycle to the debug sidebar with Ctrl+B twice.
2. Option+click on line 3.
3. Press `▶ Run`.
4. (If LiquidTerminal is not installed locally: change the command in Settings sidebar to use Terminal.app: `osascript -e 'tell application "Terminal" to do script "{cmd}"'`.)
5. External terminal window opens, runner pauses at line 3, sidebar shows `x=1`, `y=2`.
6. Press `⏵ Cont`. Program prints `3` in the terminal window, then `[Debug session ended — press Enter to close]`.

- [ ] **Step 6: Checkpoint**

Suggested message: `feat(debug): wire DebugPanel + controller into JetApp`.

---

## Task 16: End-to-end smoke test

**Files:**
- Test: `tests/debug/test_end_to_end.py`

- [ ] **Step 1: Write test**

`tests/debug/test_end_to_end.py`:
```python
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jet.debug.controller import DebugController, DebugState
from jet.debug.protocol import Paused


FIXTURE = Path(__file__).parent / "fixtures" / "simple.py"


@pytest.mark.asyncio
async def test_full_session_paused_then_continued():
    events: list = []

    def on_event(ev):
        events.append(ev)

    ctrl = DebugController(on_event=on_event)
    ctrl.toggle_breakpoint(FIXTURE, 3)

    def fake_spawn(template, argv):
        asyncio.get_event_loop()._proc = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        )

    with patch("jet.debug.controller.terminal.spawn", side_effect=fake_spawn):
        await ctrl.start(target=FIXTURE, terminal_template="{cmd}")
        for _ in range(50):
            if ctrl.state == DebugState.PAUSED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.PAUSED
        paused_events = [e for e in events if isinstance(e, Paused)]
        assert paused_events
        assert paused_events[0].line == 3
        await ctrl.continue_()
        for _ in range(50):
            if ctrl.state == DebugState.EXITED:
                break
            await asyncio.sleep(0.1)
        assert ctrl.state == DebugState.EXITED

    proc_task = getattr(asyncio.get_event_loop(), "_proc", None)
    if proc_task:
        proc = await proc_task
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/debug/test_end_to_end.py -v`
Expected: PASS.

- [ ] **Step 3: Full suite**

Run: `uv run pytest tests -v`
Expected: ALL PASS.

- [ ] **Step 4: Checkpoint**

Suggested message: `test(debug): end-to-end controller+runner smoke test`.

---

## Task 17: README documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Debug section**

Append to `README.md`:

```markdown
## Debug (Python)

`jet` includes a Python debugger sidebar.

- Cycle to the **Debug** sidebar with `Ctrl+B`.
- `Option+click` a line in the editor to toggle a breakpoint. Fallback: `Shift+click`.
- Press **▶ Run** to start. The active file is launched inside an external terminal app (default: LiquidTerminal.app) where you can see prints and type into `input()`.
- The sidebar shows local + global variables when paused.
- Buttons: **⏵ Continue**, **↷ Step over**, **↘ Step into**, **↖ Step out**, **■ Stop**.
- The current execution line is highlighted in the gutter (▶ when line numbers are off, otherwise the line number is recolored).

### Changing the external terminal

Open the Settings sidebar (`Ctrl+B` once from the tree). The **Debug terminal command** field accepts any shell template containing `{cmd}`. Examples:

- macOS Terminal.app: `osascript -e 'tell application "Terminal" to do script "{cmd}"'`
- iTerm2: `osascript -e 'tell application "iTerm" to create window with default profile command "{cmd}"'`
- Linux (GNOME): `gnome-terminal -- bash -c "{cmd}; read"`
```

- [ ] **Step 2: Checkpoint**

Suggested message: `docs: document debug sidebar usage`.

---

## Self-Review

Spec coverage check:
- Two-process architecture → Task 3 (runner) + Task 8 (controller) ✓
- Runner inside external terminal → Task 7 + Task 8 (controller calls terminal.spawn with runner argv) ✓
- JSON-lines protocol with all 10 messages → Task 2 ✓
- bdb subclass with continue/step_over/step_into/step_out/stop → Task 3 + Task 5 ✓
- Variables: locals + filtered globals → Task 3 (runner emits) + Task 4 (test) + Task 14 (panel renders) ✓
- Stack info → Task 3 (emitted), Task 4 (asserted) ✓
- Exception handling → Task 6 ✓
- DebugPanel with buttons, status, locals/globals/BP sections → Task 14 ✓
- Editor: breakpoints + current_exec_line state → Task 11 ✓
- Editor gutter rendering (theme colors / glyphs) → Task 12 ✓
- Option+click to toggle BP → Task 13 ✓
- Editor read-only on pause → Task 15 (in `_on_debug_event`) ✓
- Sidebar cycle (tree → settings → debug) → Task 15 ✓
- EditorConfig.debug_terminal_command + SettingsPanel input → Task 10 ✓
- Unsaved/untitled → temp file → Task 8 (controller `buffer_text` branch) + Task 15 (app passes buffer text) ✓
- Run button disabled when state != idle → Task 14 (`_refresh_state`) ✓
- Crash detection (EOF without Exited) → Task 8 (`_read_loop` EOF branch) ✓
- Terminal spawn errors → Task 7 + Task 8 (controller catches `TerminalSpawnError`) ✓
- Keep external terminal open after exit → Task 3 (final `input()` in runner) ✓
- get_frame_vars marked NOT in MVP → confirmed (no task implements it) ✓

Placeholder scan: no `TBD`/`TODO`/"add appropriate"/"similar to". Note in Task 12 about Textual gutter API is a *fallback instruction*, not a placeholder — it tells the engineer exactly what to do if `render_line` doesn't work cleanly. Acceptable.

Type consistency: `DebugController.toggle_breakpoint`, `get_breakpoints`, `start`, `continue_`, `step_over`, `step_into`, `step_out`, `stop` — used consistently across Tasks 8/14/15. `JetEditor.set_breakpoints`, `set_current_exec_line`, `breakpoints`, `current_exec_line`, `request_breakpoint_toggle` — consistent across 11/12/13/15. Protocol message types — consistent everywhere.

Plan is complete and consistent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-python-debug-sidebar.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
