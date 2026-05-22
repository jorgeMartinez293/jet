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
