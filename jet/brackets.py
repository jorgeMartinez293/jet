"""Auto-close brackets / quotes — pure logic, testable without Textual."""

from __future__ import annotations


PAIRS: dict[str, str] = {
    "(": ")",
    "[": "]",
    "{": "}",
    '"': '"',
    "'": "'",
    "`": "`",
}

OPENERS: frozenset[str] = frozenset(PAIRS.keys())
CLOSERS: frozenset[str] = frozenset(PAIRS.values())

_QUOTES: frozenset[str] = frozenset({'"', "'", "`"})


def closer_for(opener: str) -> str | None:
    return PAIRS.get(opener)


def opener_for(closer: str) -> str | None:
    for o, c in PAIRS.items():
        if c == closer and o != c:
            return o
    return None


def should_skip_over(line: str, col: int, typed: str) -> bool:
    """True if `typed` is a closer and the next char already equals it.

    Lets user type the close char to "move past" the auto-inserted closer
    without producing a duplicate.
    """
    if typed not in CLOSERS:
        return False
    if col >= len(line):
        return False
    return line[col] == typed


def should_auto_close(line: str, col: int, opener: str) -> bool:
    """Decide whether typing `opener` should also insert its closer.

    Heuristics:
    - Always auto-close brackets `( [ {`.
    - For quotes: don't auto-close if previous char is an alphanumeric/underscore
      (likely an apostrophe in a word) or if we're already inside an open-of-same
      (avoid doubling triple quotes naturally — user can type the third manually).
    - Don't auto-close if the next character is a word/identifier char (would
      shadow incoming text).
    """
    if opener not in OPENERS:
        return False

    next_ch = line[col] if col < len(line) else ""
    if next_ch and (next_ch.isalnum() or next_ch == "_"):
        return False

    if opener in _QUOTES:
        prev_ch = line[col - 1] if col > 0 else ""
        if prev_ch and (prev_ch.isalnum() or prev_ch == "_"):
            return False
    return True


def should_delete_pair(line: str, col: int) -> bool:
    """Backspace deletes BOTH chars if cursor sits between an empty pair."""
    if col <= 0 or col >= len(line):
        return False
    prev_ch = line[col - 1]
    next_ch = line[col]
    return PAIRS.get(prev_ch) == next_ch
