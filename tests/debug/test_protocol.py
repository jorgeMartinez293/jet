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
