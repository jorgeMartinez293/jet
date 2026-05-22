"""Syntax-only TextAreaThemes. No background — terminal/app background shows through."""

from __future__ import annotations

from rich.style import Style
from textual.widgets.text_area import TextAreaTheme


def _build(
    name: str,
    *,
    fg: str,
    comment: str,
    keyword: str,
    string: str,
    func: str,
    number: str,
    type_: str,
    builtin: str,
    operator: str,
    punct: str,
    selection: str,
    gutter: str,
    gutter_hl: str,
) -> TextAreaTheme:
    """Build a syntax theme. Only foreground colors are set; backgrounds stay transparent."""
    return TextAreaTheme(
        name=name,
        base_style=Style(color=fg),
        gutter_style=Style(color=gutter),
        cursor_style=Style(),
        cursor_line_style=Style(),
        cursor_line_gutter_style=Style(color=gutter_hl),
        bracket_matching_style=Style(color=fg, underline=True),
        selection_style=Style(bgcolor=selection),
        syntax_styles={
            "string": Style(color=string),
            "string.documentation": Style(color=string, italic=True),
            "comment": Style(color=comment, italic=True),
            "keyword": Style(color=keyword),
            "keyword.function": Style(color=keyword),
            "keyword.return": Style(color=keyword),
            "keyword.operator": Style(color=keyword),
            "conditional": Style(color=keyword),
            "repeat": Style(color=keyword),
            "exception": Style(color=keyword),
            "include": Style(color=keyword),
            "operator": Style(color=operator),
            "number": Style(color=number),
            "float": Style(color=number),
            "boolean": Style(color=builtin, italic=True),
            "constant.builtin": Style(color=builtin, italic=True),
            "variable.builtin": Style(color=builtin, italic=True),
            "type": Style(color=type_),
            "type.builtin": Style(color=type_, italic=True),
            "type.class": Style(color=type_),
            "class": Style(color=type_),
            "function": Style(color=func),
            "function.call": Style(color=func),
            "method": Style(color=func),
            "method.call": Style(color=func),
            "punctuation.bracket": Style(color=punct),
            "punctuation.delimiter": Style(color=punct),
            "punctuation.special": Style(color=punct),
            "tag": Style(color=keyword),
            "json.label": Style(color=keyword),
            "yaml.field": Style(color=keyword),
            "heading": Style(color=keyword, bold=True),
            "bold": Style(bold=True),
            "italic": Style(italic=True),
            "link.uri": Style(color=type_, underline=True),
            "inline_code": Style(color=string),
        },
    )


NEON = _build(
    "neon",
    fg="#f5f5f5",
    comment="#6a7384",
    keyword="#ff4f8b",
    string="#d6ff5e",
    func="#5eeaff",
    number="#ffae42",
    type_="#c084fc",
    builtin="#ff7eb6",
    operator="#f5f5f5",
    punct="#9aa5b1",
    selection="#2a2f3a",
    gutter="#3a3f4b",
    gutter_hl="#cdd6f4",
)

PASTEL = _build(
    "pastel",
    fg="#d8d8d8",
    comment="#6c7387",
    keyword="#c39bd3",
    string="#a7d7a7",
    func="#95c8e6",
    number="#f1c27d",
    type_="#b5b3e5",
    builtin="#f0a8b5",
    operator="#d8d8d8",
    punct="#888d96",
    selection="#2c3140",
    gutter="#3a3f4b",
    gutter_hl="#c8cdd9",
)

MONO = _build(
    "mono",
    fg="#e8e8e8",
    comment="#6a6a6a",
    keyword="#ffffff",
    string="#b8b8b8",
    func="#d4d4d4",
    number="#a8a8a8",
    type_="#c4c4c4",
    builtin="#d0d0d0",
    operator="#909090",
    punct="#787878",
    selection="#333333",
    gutter="#5a5a5a",
    gutter_hl="#bdbdbd",
)

SUNSET = _build(
    "sunset",
    fg="#f5e6d3",
    comment="#7a6a5a",
    keyword="#ff6b6b",
    string="#ffd166",
    func="#f78c6b",
    number="#ef476f",
    type_="#ffa07a",
    builtin="#ffb380",
    operator="#f5e6d3",
    punct="#9a8770",
    selection="#3a2820",
    gutter="#6e574a",
    gutter_hl="#d6b89a",
)

FOREST = _build(
    "forest",
    fg="#d4e4d4",
    comment="#5a705a",
    keyword="#7fb069",
    string="#d4d970",
    func="#74a892",
    number="#e08d3c",
    type_="#a3c9a8",
    builtin="#c7d99f",
    operator="#d4e4d4",
    punct="#889988",
    selection="#2a352a",
    gutter="#4d5e51",
    gutter_hl="#a8bfa3",
)

THEMES: dict[str, TextAreaTheme] = {t.name: t for t in [NEON, PASTEL, MONO, SUNSET, FOREST]}
