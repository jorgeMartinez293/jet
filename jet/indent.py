"""Auto-indent rules — pure logic, testable without Textual.

`compute_newline_insert(prev_line, col, language)` returns the text to insert when
the user presses Enter, given the line being broken at `col`. The return is the
literal string to put in place of `\\n`, e.g. `"\\n        "`.
"""

from __future__ import annotations


INDENT_UNIT = "    "  # 4 spaces

_PY_DEDENT_KEYWORDS: tuple[str, ...] = (
    "return",
    "pass",
    "raise",
    "break",
    "continue",
)


def leading_whitespace(line: str) -> str:
    i = 0
    while i < len(line) and line[i] in (" ", "\t"):
        i += 1
    return line[:i]


def _strip_inline_comment(line: str) -> str:
    # Naive: strip after '#' not inside string. Good enough for indent decisions.
    in_str: str | None = None
    out: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"'):
                in_str = ch
                out.append(ch)
            elif ch == "#":
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _ends_with_colon(line: str) -> bool:
    stripped = _strip_inline_comment(line).rstrip()
    return stripped.endswith(":")


def _open_brackets_delta(line: str) -> int:
    """Net count of (/[/{ opens not yet closed on this line, ignoring strings."""
    in_str: str | None = None
    depth = 0
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == "\\" and i + 1 < len(line):
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"'):
                in_str = ch
            elif ch == "#":
                break
            elif ch in ("(", "[", "{"):
                depth += 1
            elif ch in (")", "]", "}"):
                depth -= 1
        i += 1
    return depth


def compute_newline_indent(prev_line: str, language: str | None) -> str:
    """Return indent string (spaces) for the new line created by Enter."""
    base = leading_whitespace(prev_line)

    if language != "python":
        # Generic: copy previous indent, +1 unit if line ends with an opener.
        stripped = prev_line.rstrip()
        if stripped and stripped[-1] in ("(", "[", "{", ":"):
            return base + INDENT_UNIT
        return base

    extra = ""
    stripped = _strip_inline_comment(prev_line).rstrip()

    if _ends_with_colon(prev_line):
        extra = INDENT_UNIT
    elif _open_brackets_delta(prev_line) > 0:
        extra = INDENT_UNIT
    else:
        first = stripped.lstrip().split(" ", 1)[0].rstrip(":")
        if first in _PY_DEDENT_KEYWORDS and len(base) >= len(INDENT_UNIT):
            return base[: -len(INDENT_UNIT)]

    return base + extra


def should_open_block(prev_line: str, next_char: str) -> bool:
    """When Enter is pressed between matching brackets like `{|}`, the editor
    should produce two newlines so the closer ends up on its own dedented line.
    """
    stripped = prev_line.rstrip()
    if not stripped:
        return False
    last = stripped[-1]
    pairs = {"(": ")", "[": "]", "{": "}"}
    return last in pairs and next_char == pairs[last]
