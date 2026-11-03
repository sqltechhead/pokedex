"""Bitmap fonts (BDF) for the Pico, drawn from DejaVu Sans with Pillow.

CircuitPython can't render TrueType, so each size the screens use becomes
its own BDF file holding only the characters that actually appear: every
name and entry on the card, plus the firmware's own labels and button hints.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).parent / "fonts"
REGULAR = FONTS_DIR / "DejaVuSans.ttf"
BOLD = FONTS_DIR / "DejaVuSans-Bold.ttf"


@dataclass(frozen=True)
class FontSpec:
    filename: str
    ttf: Path
    size: int


# Must match FONT_FILES in firmware/lib/dex/screens.py.
FONTS = (
    FontSpec("title.bdf", BOLD, 18),
    FontSpec("name.bdf", BOLD, 16),
    FontSpec("body.bdf", REGULAR, 13),
    FontSpec("bold.bdf", BOLD, 12),
    FontSpec("small.bdf", REGULAR, 11),
)
ASCII = "".join(chr(c) for c in range(32, 127))


def charset(*texts: str) -> str:
    """Printable ASCII plus every other character in texts, sorted."""
    chars = set(ASCII)
    for text in texts:
        chars.update(c for c in text if c.isprintable())
    return "".join(sorted(chars))


def write_bdf(spec: FontSpec, chars: str, dest: Path) -> None:
    font = ImageFont.truetype(str(spec.ttf), spec.size)
    glyphs = [_glyph(font, c) for c in chars]
    widest = max(g.width for g in glyphs)
    # The glyphs' real extent, not Pillow's getmetrics(), which adds line spacing:
    # adafruit_display_text's bitmap_label positions text by FONT_ASCENT, so
    # extra space there draws every label several pixels too low.
    ascent = max(g.height + g.y_offset for g in glyphs)
    descent = max(-g.y_offset for g in glyphs)
    lines = [
        "STARTFONT 2.1",
        f"FONT -DejaVu-{spec.ttf.stem}-{spec.size}",
        f"SIZE {spec.size} 75 75",
        f"FONTBOUNDINGBOX {widest} {ascent + descent} 0 {-descent}",
        "STARTPROPERTIES 4",
        f"FONT_ASCENT {ascent}",
        f"FONT_DESCENT {descent}",
        'CHARSET_REGISTRY "ISO10646"',
        'CHARSET_ENCODING "1"',
        "ENDPROPERTIES",
        f"CHARS {len(glyphs)}",
    ]
    for g in glyphs:
        lines += [
            f"STARTCHAR U+{g.code:04X}",
            f"ENCODING {g.code}",
            f"SWIDTH {g.advance * 1000 // spec.size} 0",
            f"DWIDTH {g.advance} 0",
            f"BBX {g.width} {g.height} {g.x_offset} {g.y_offset}",
            "BITMAP",
            *g.rows,
            "ENDCHAR",
        ]
    lines.append("ENDFONT")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="ascii")


@dataclass(frozen=True)
class Glyph:
    code: int
    advance: int
    width: int
    height: int
    x_offset: int
    y_offset: int
    """Bottom row's distance above the baseline (negative for descenders)."""
    rows: tuple[str, ...]
    """Each row as hex, padded to whole bytes, most significant bit leftmost."""


def _glyph(font: ImageFont.FreeTypeFont, char: str) -> Glyph:
    advance = round(font.getlength(char))
    left, top, right, bottom = font.getbbox(char, anchor="ls")
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:  # a space: one blank pixel, as displayio has no 0x0 bitmap
        return Glyph(ord(char), advance, 1, 1, 0, 0, ("00",))
    image = Image.new("L", (width, height), 0)
    ImageDraw.Draw(image).text((-left, -top), char, font=font, fill=255, anchor="ls")
    pixels = image.load()
    rows = []
    for y in range(height):
        bits = 0
        for x in range(width):
            bits = bits << 1 | (pixels[x, y] >= 128)
        padded = (width + 7) // 8 * 8
        rows.append(f"{bits << (padded - width):0{padded // 4}X}")
    return Glyph(ord(char), advance, width, height, left, -bottom, tuple(rows))
