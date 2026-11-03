"""Sprites and artwork as small 8-bit BMPs, the format displayio streams from the card.

Colour 0 of each palette is transparent. Soft edges are blended onto the
panel colour the Pico draws them on, since a BMP pixel is either fully
shown or fully transparent.
"""

from pathlib import Path

from PIL import Image

PANEL = (30, 37, 45)
"""dex.theme.PANEL: the background behind every picture on the device."""
TRANSPARENT = (255, 0, 255)
"""Palette colour 0; never drawn, so any colour would do."""
SILHOUETTE = (8, 10, 12)
"""The quiz's "Who's that Pokémon?" shadow."""


def to_bmp(source: Path, dest: Path, box: int, *, pixel_art: bool = False) -> None:
    """Fit the image in a box x box square and save it as an 8-bit BMP.

    pixel_art trims the sprite's empty border and enlarges it by a whole
    number with no smoothing, so game sprites stay crisp.
    """
    image = Image.open(source).convert("RGBA")
    if pixel_art:
        image = _enlarge_crisp(image, box)
    else:
        image.thumbnail((box, box), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    indexed(image).save(dest, format="BMP")


def silhouette(source: Path, dest: Path, box: int) -> None:
    """The artwork's outline filled with one dark colour, as a 2-colour BMP."""
    image = Image.open(source).convert("RGBA")
    image.thumbnail((box, box), Image.Resampling.LANCZOS)
    solid = image.getchannel("A").point(lambda a: 1 if a >= 128 else 0)
    result = Image.frombytes("P", image.size, solid.tobytes())
    palette = [*TRANSPARENT, *SILHOUETTE]
    result.putpalette(palette + [0] * (768 - len(palette)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    result.save(dest, format="BMP")


def _enlarge_crisp(image: Image.Image, box: int) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    if bbox:
        image = image.crop(bbox)
    width, height = image.size
    factor = box // max(width, height)
    if factor >= 1:
        return image.resize((width * factor, height * factor), Image.Resampling.NEAREST)
    image.thumbnail((box, box), Image.Resampling.LANCZOS)
    return image


def indexed(image: Image.Image) -> Image.Image:
    """An RGBA image as palette indices 1-255, with 0 for transparent pixels."""
    alpha = image.getchannel("A")
    background = Image.new("RGBA", image.size, (*PANEL, 255))
    flat = Image.alpha_composite(background, image).convert("RGB")
    quantized = flat.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    colors = quantized.getpalette()[: 255 * 3]
    shifted = Image.frombytes("L", image.size, quantized.tobytes()).point(lambda i: i + 1)
    shifted.paste(0, mask=alpha.point(lambda a: 255 if a < 128 else 0))
    result = Image.frombytes("P", image.size, shifted.tobytes())
    palette = [*TRANSPARENT, *colors]
    result.putpalette(palette + [0] * (768 - len(palette)))
    return result
