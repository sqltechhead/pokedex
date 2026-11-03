"""pokedex-sdcard: building the Pico's microSD card from data/."""

import json
import math
import struct
import wave

import pytest
from PIL import Image

from pokedex.db import PokedexDB
from pokedex.models import BaseStats, Pokemon
from pokedex.paths import DataPaths
from pokedex.sdcard import audio, cli, entries, fonts, images

STATS = BaseStats(hp=35, attack=55, defense=40, sp_attack=50, sp_defense=50, speed=90)


def test_search_keys():
    assert entries.search_key("Mr. Mime") == "mrmime"
    assert entries.search_key("Flabébé") == "flabebe"
    assert entries.search_key("Nidoran♀") == "nidoran"
    assert entries.search_key("Type: Null") == "typenull"


def sprite(path, size=(96, 96)) -> None:
    """A red square on a transparent background, with a soft edge."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(30, 66):
        for y in range(30, 66):
            image.putpixel((x, y), (220, 30, 30, 255))
    image.putpixel((29, 40), (220, 30, 30, 100))  # mostly transparent edge pixel
    image.save(path)


class TestImages:
    def test_pixel_art_is_trimmed_and_enlarged_crisply(self, tmp_path):
        sprite(tmp_path / "s.png")
        images.to_bmp(tmp_path / "s.png", tmp_path / "s.bmp", 112, pixel_art=True)
        out = Image.open(tmp_path / "s.bmp")
        assert out.mode == "P"
        assert out.size == (111, 108)  # 37x36 after trimming, enlarged 3x
        assert out.getpixel((0, 0)) == 0  # the transparent edge pixel
        assert out.getpalette()[:3] == list(images.TRANSPARENT)
        red = out.getpalette()[out.getpixel((50, 50)) * 3 : out.getpixel((50, 50)) * 3 + 3]
        assert red == [220, 30, 30]

    def test_artwork_shrinks_to_fit(self, tmp_path):
        sprite(tmp_path / "a.png", size=(475, 475))
        images.to_bmp(tmp_path / "a.png", tmp_path / "a.bmp", 160)
        out = Image.open(tmp_path / "a.bmp")
        assert out.size == (160, 160)
        assert out.getpixel((0, 0)) == 0

    def test_bmp_is_8_bit_with_a_plain_header(self, tmp_path):
        sprite(tmp_path / "s.png")
        images.to_bmp(tmp_path / "s.png", tmp_path / "s.bmp", 48)
        header = (tmp_path / "s.bmp").read_bytes()[:30]
        assert header[:2] == b"BM"
        header_size, _, _, _, bits = struct.unpack("<IiiHH", header[14:30])
        assert (header_size, bits) == (40, 8)  # what displayio.OnDiskBitmap reads


def tone(path, rate=48000, seconds=0.2, channels=2) -> None:
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * n / rate))) * channels
        for n in range(int(rate * seconds))
    )
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)


def test_audio_becomes_mono_16_bit_at_the_pico_rate(tmp_path):
    tone(tmp_path / "in.wav")
    audio.to_wav(tmp_path / "in.wav", tmp_path / "out.wav")
    with wave.open(str(tmp_path / "out.wav")) as out:
        assert out.getnchannels() == 1
        assert out.getsampwidth() == 2
        assert out.getframerate() == audio.SAMPLE_RATE
        assert abs(out.getnframes() - audio.SAMPLE_RATE * 0.2) < 100
    assert (tmp_path / "out.wav").read_bytes()[36:40] == b"data"  # no extra chunks


def parse_bdf(text: str) -> dict[int, dict]:
    glyphs, current = {}, None
    lines = iter(text.splitlines())
    for line in lines:
        key, _, value = line.partition(" ")
        if key == "ENCODING":
            current = {"code": int(value)}
        elif key in ("BBX", "DWIDTH"):
            current[key] = [int(v) for v in value.split()]
        elif key == "BITMAP":
            current["rows"] = []
            for row in lines:
                if row == "ENDCHAR":
                    break
                current["rows"].append(row)
            glyphs[current["code"]] = current
    return glyphs


def test_bdf_font(tmp_path):
    spec = fonts.FontSpec("body.bdf", fonts.REGULAR, 13)
    chars = fonts.charset("Flabébé ♀")
    fonts.write_bdf(spec, chars, tmp_path / "body.bdf")
    text = (tmp_path / "body.bdf").read_text()
    head = text.splitlines()[:11]
    assert head[0] == "STARTFONT 2.1"
    assert any(line.startswith("FONTBOUNDINGBOX ") for line in head)  # read from the top
    glyphs = parse_bdf(text)
    assert set(glyphs) == {ord(c) for c in chars}
    assert ord("é") in glyphs and ord("♀") in glyphs

    letter_l = glyphs[ord("l")]
    width, height, _, y_offset = letter_l["BBX"]
    assert height == len(letter_l["rows"]) >= 8
    assert y_offset == 0  # sits on the baseline
    assert all(len(row) == (width + 7) // 8 * 2 for row in letter_l["rows"])
    assert all(int(row, 16) for row in letter_l["rows"])  # a solid vertical stroke
    assert glyphs[ord("p")]["BBX"][3] < 0  # descender
    assert glyphs[ord(" ")]["DWIDTH"][0] > 0


def test_charset_covers_ascii_and_extras():
    chars = fonts.charset("é\n▲")
    assert "A" in chars and "~" in chars and "é" in chars and "▲" in chars
    assert "\n" not in chars


@pytest.fixture
def data(tmp_path) -> DataPaths:
    paths = DataPaths(tmp_path / "data")
    paths.sprites.mkdir(parents=True)
    paths.cries.mkdir()
    sprite(paths.sprite_file(25))
    tone(paths.cry_file(25).with_suffix(".wav"))
    pikachu = Pokemon(
        id=25,
        name="Pikachu",
        genus="Mouse Pokémon",
        type1="electric",
        height_dm=4,
        weight_hg=60,
        stats=STATS,
        flavor_text="It keeps its tail raised.",
        sprite_path="sprites/0025.png",
        cry_path="cries/0025.wav",
        narration_path="narration/0025.ogg",  # listed but missing: skipped
    )
    with PokedexDB(paths.db) as db:
        db.upsert(pikachu)
    return paths


def test_builds_a_card(tmp_path, data: DataPaths, capsys):
    out = tmp_path / "sd"
    assert cli.main(["--data", str(data.root), "--out", str(out)]) == 0
    card = out / "pokedex"
    assert (card / "index.tsv").read_text() == "25\tPikachu\tpikachu\telectric\t\n"
    entry = json.loads((card / "mon" / "0025.json").read_text())
    assert entry["stats"] == [35, 55, 40, 50, 50, 90]
    assert entry["chain"] is None
    for folder in ("art", "spr", "ev72", "ev44", "ev26"):
        assert Image.open(card / folder / "0025.bmp").mode == "P"
    assert (card / "cry" / "0025.wav").exists()
    assert not (card / "say").exists()
    assert {p.name for p in (card / "fonts").iterdir()} == {s.filename for s in fonts.FONTS}

    # The fonts cover the firmware's own labels, like the ▲▼ button hints.
    body = (card / "fonts" / "body.bdf").read_text()
    assert f"ENCODING {ord('▲')}" in body

    capsys.readouterr()
    assert cli.main(["--data", str(data.root), "--out", str(out)]) == 0
    assert "up to date" in capsys.readouterr().out


def test_needs_a_database(tmp_path, capsys):
    assert cli.main(["--data", str(tmp_path), "--out", str(tmp_path / "sd")]) == 1
    assert "pokedex-fetch" in capsys.readouterr().err
