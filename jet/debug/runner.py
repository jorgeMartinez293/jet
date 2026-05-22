"""jet.debug.runner — child process running user code under bdb.

Started by an external terminal. Connects back to the editor via a UNIX
socket. Reads commands, emits events. stdin/stdout/stderr are the
external terminal's tty.
"""

from __future__ import annotations

import bdb
import reprlib
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
        # When running freely (no active step), only pause at real breakpoints.
        if self._step_mode is None and not self.break_here(frame):
            return
        self._pause(frame)

    def user_return(self, frame, return_value) -> None:
        del frame, return_value
        if self._step_mode == "out":
            # We're at the return of the function being stepped out of. Don't
            # pause here (that would still be inside the callee). Switch to a
            # plain step so the very next user_line fires in the caller frame,
            # and pause there.
            self._step_mode = "over"
            self.set_step()

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
        if sys.stdin.isatty():
            try:
                input("\n[Debug session ended — press Enter to close]")
            except (EOFError, KeyboardInterrupt):
                pass
        io.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
