from textual.widgets.text_area import TextAreaTheme

from .arctic import THEME as ARCTIC
from .ember import THEME as EMBER
from .forest import THEME as FOREST
from .mono import THEME as MONO
from .neon import THEME as NEON
from .ocean import THEME as OCEAN
from .pastel import THEME as PASTEL
from .sakura import THEME as SAKURA
from .sunset import THEME as SUNSET

THEMES: dict[str, TextAreaTheme] = {
    t.name: t
    for t in [NEON, PASTEL, MONO, SUNSET, FOREST, OCEAN, EMBER, ARCTIC, SAKURA]
}
