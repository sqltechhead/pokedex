"""Colours and fonts for the Pokédex screen."""

from dataclasses import dataclass
from pathlib import Path

Color = tuple[int, int, int]

FONTS_DIR = Path(__file__).parent / "fonts"

# Canonical type order, also used to cycle the type filter.
TYPE_COLORS: dict[str, Color] = {
    "normal": (168, 167, 122),
    "fire": (238, 129, 48),
    "water": (99, 144, 240),
    "electric": (247, 208, 44),
    "grass": (122, 199, 76),
    "ice": (150, 217, 214),
    "fighting": (194, 46, 40),
    "poison": (163, 62, 161),
    "ground": (226, 191, 101),
    "flying": (169, 143, 243),
    "psychic": (249, 85, 135),
    "bug": (166, 185, 26),
    "rock": (182, 161, 54),
    "ghost": (115, 87, 151),
    "dragon": (111, 53, 252),
    "dark": (112, 87, 70),
    "steel": (183, 183, 206),
    "fairy": (214, 133, 173),
}
TYPE_ORDER = tuple(TYPE_COLORS)

STAT_LABELS = {
    "hp": "HP",
    "attack": "ATK",
    "defense": "DEF",
    "sp_attack": "SP.A",
    "sp_defense": "SP.D",
    "speed": "SPE",
}


@dataclass(frozen=True)
class Theme:
    bg: Color = (16, 20, 24)
    panel: Color = (30, 37, 45)
    panel_light: Color = (44, 54, 65)
    accent: Color = (220, 10, 45)
    text: Color = (240, 242, 245)
    muted: Color = (150, 160, 172)
    # DejaVu Sans covers the ♀/♂ in Nidoran's names and the ▲◀ button hints.
    font_regular: Path = FONTS_DIR / "DejaVuSans.ttf"
    font_bold: Path = FONTS_DIR / "DejaVuSans-Bold.ttf"

    def type_color(self, type_name: str) -> Color:
        return TYPE_COLORS.get(type_name, self.muted)

    def stat_color(self, value: int) -> Color:
        for limit, color in (
            (50, (243, 68, 68)),
            (80, (255, 127, 15)),
            (100, (255, 221, 87)),
            (120, (160, 229, 21)),
        ):
            if value < limit:
                return color
        return (35, 205, 94)

    @staticmethod
    def ink_on(color: Color) -> Color:
        """Black or white, whichever reads better on color."""
        r, g, b = color
        return (20, 20, 20) if 0.299 * r + 0.587 * g + 0.114 * b > 165 else (255, 255, 255)
