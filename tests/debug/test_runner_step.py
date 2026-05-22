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
