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
