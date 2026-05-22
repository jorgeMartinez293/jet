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
