"""Colours for the Pokédex screen, as 0xRRGGBB."""

BG = 0x101418
PANEL = 0x1E252D
PANEL_LIGHT = 0x2C3641
ACCENT = 0xDC0A2D
TEXT = 0xF0F2F5
MUTED = 0x96A0AC
WHITE = 0xFFFFFF
LENS = 0x3D9BE0
LOW_BATTERY = 0xFFD23C
"""Yellow, as red wouldn't show on the red header."""

# Canonical type order, also used to cycle the type filter and to number
# types compactly in memory (see dex.index).
TYPE_ORDER = (
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
    "dark",
    "steel",
    "fairy",
)
TYPE_COLORS = {
    "normal": 0xA8A77A,
    "fire": 0xEE8130,
    "water": 0x6390F0,
    "electric": 0xF7D02C,
    "grass": 0x7AC74C,
    "ice": 0x96D9D6,
    "fighting": 0xC22E28,
    "poison": 0xA33EA1,
    "ground": 0xE2BF65,
    "flying": 0xA98FF3,
    "psychic": 0xF95587,
    "bug": 0xA6B91A,
    "rock": 0xB6A136,
    "ghost": 0x735797,
    "dragon": 0x6F35FC,
    "dark": 0x705746,
    "steel": 0xB7B7CE,
    "fairy": 0xD685AD,
}

STAT_LABELS = ("HP", "ATK", "DEF", "SP.A", "SP.D", "SPE")
"""In the order the SD card stores stats."""


def type_color(type_name):
    return TYPE_COLORS.get(type_name, MUTED)


def stat_color(value):
    for limit, color in ((50, 0xF34444), (80, 0xFF7F0F), (100, 0xFFDD57), (120, 0xA0E515)):
        if value < limit:
            return color
    return 0x23CD5E


def ink_on(color):
    """Black or white, whichever reads better on color."""
    r, g, b = color >> 16, (color >> 8) & 0xFF, color & 0xFF
    return 0x141414 if 299 * r + 587 * g + 114 * b > 165000 else WHITE
