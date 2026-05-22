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
