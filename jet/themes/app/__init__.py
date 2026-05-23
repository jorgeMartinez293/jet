from textual.theme import Theme

from .coal import THEME as COAL
from .ink import THEME as INK
from .midnight import THEME as MIDNIGHT
from .parchment import THEME as PARCHMENT
from .slate import THEME as SLATE
from .transparent import DISPLAY_NAME as _TRANSPARENT_DISPLAY, TEXTUAL_NAME as _TRANSPARENT_TEXTUAL

_OPAQUE: list[Theme] = [MIDNIGHT, COAL, SLATE, PARCHMENT, INK]


def _make_clear(t: Theme) -> Theme:
    """Transparent variant: keeps accent palette, defers background to terminal."""
    return Theme(
        name=f"{t.name}-clear",
        primary=t.primary,
        secondary=t.secondary,
        background=None,
        surface=None,
        panel=None,
        foreground=t.foreground,
        warning=t.warning,
        error=t.error,
        success=t.success,
        accent=t.accent,
        dark=t.dark,
    )


# All custom Theme objects to register with app.register_theme()
CUSTOM_THEMES: list[Theme] = _OPAQUE + [_make_clear(t) for t in _OPAQUE]

# All selectable app themes: (display_name, textual_theme_name)
APP_THEMES: list[tuple[str, str]] = (
    [(_TRANSPARENT_DISPLAY, _TRANSPARENT_TEXTUAL)]
    + [(t.name, t.name) for t in CUSTOM_THEMES]
)
