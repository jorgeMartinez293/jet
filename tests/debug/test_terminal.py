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
