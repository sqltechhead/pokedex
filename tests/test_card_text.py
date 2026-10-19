from pathlib import Path

import pytest

pytest.importorskip("onnxruntime")
pytest.importorskip("scipy")
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from pokedex.recognizer.card_text import MODEL_DIR, CardReader, normalize_name  # noqa: E402
from pokedex.recognizer.matcher import Match  # noqa: E402
from pokedex.recognizer.scanner import Scanner  # noqa: E402
from pokedex.ui.theme import FONTS_DIR  # noqa: E402

MODELS = Path(__file__).parents[1] / "data" / "models" / MODEL_DIR
NAMES = [
    (1, "Bulbasaur"),
    (2, "Ivysaur"),
    (3, "Venusaur"),
    (23, "Ekans"),
    (122, "Mr. Mime"),
    (83, "Farfetch’d"),
]


def test_normalize_name():
    assert normalize_name("Mr. Mime") == "mrmime"
    assert normalize_name("Farfetch’d") == "farfetchd"
    assert normalize_name("Flabébé") == "flabebe"


class TestMatchName:
    """Matching needs no models: build a reader without loading them."""

    @pytest.fixture
    def reader(self) -> CardReader:
        reader = CardReader.__new__(CardReader)
        reader._names = [(pid, normalize_name(name)) for pid, name in NAMES]
        return reader

    def test_exact_and_misread(self, reader: CardReader):
        assert reader.match_name("Bulbasaur").pokemon_id == 1
        assert reader.match_name("Bulbasaor").pokemon_id == 1  # one letter misread
        assert reader.match_name("Mr. Mime").pokemon_id == 122
        assert reader.match_name("Farfetchd").pokemon_id == 83

    def test_name_inside_a_longer_line(self, reader: CardReader):
        assert reader.match_name("BASIC Ekans HP70").pokemon_id == 23

    def test_non_names_are_ignored(self, reader: CardReader):
        assert reader.match_name("Acid Spray") is None
        assert reader.match_name("80") is None
        assert reader.match_name("Ivy") is None  # too short and too different


def fake_card(name: str, small_print: str = "") -> Image.Image:
    card = Image.new("RGB", (360, 360), (160, 200, 90))
    draw = ImageDraw.Draw(card)
    draw.rectangle((30, 20, 330, 340), fill=(225, 235, 200))
    draw.text(
        (50, 32),
        name,
        fill=(20, 20, 20),
        font=ImageFont.truetype(str(FONTS_DIR / "DejaVuSans-Bold.ttf"), 30),
    )
    draw.rectangle((50, 90, 310, 220), fill=(90, 140, 200))
    if small_print:
        draw.text(
            (50, 250),
            small_print,
            fill=(40, 40, 40),
            font=ImageFont.truetype(str(FONTS_DIR / "DejaVuSans.ttf"), 14),
        )
    return card


needs_models = pytest.mark.skipif(not MODELS.exists(), reason="OCR models not downloaded")


@pytest.fixture(scope="module")
def card_reader() -> CardReader:
    return CardReader(MODELS, NAMES)


@needs_models
def test_reads_the_printed_name(card_reader: CardReader):
    found = card_reader.find_name(fake_card("Bulbasaur"))
    assert found is not None and found.pokemon_id == 1


@needs_models
def test_big_title_beats_small_print(card_reader: CardReader):
    found = card_reader.find_name(fake_card("Venusaur", small_print="Evolves from Ivysaur"))
    assert found is not None and found.pokemon_id == 3


@needs_models
def test_no_text_means_no_name(card_reader: CardReader):
    assert card_reader.find_name(Image.new("RGB", (360, 360), (200, 120, 60))) is None


class FakeRecognizer:
    def __init__(self) -> None:
        self.calls = 0

    def identify(self, image, top=3):
        self.calls += 1
        return [Match(25, 0.3, 0.9)]


class FakeReader:
    def __init__(self, found) -> None:
        self.found = found

    def find_name(self, image):
        return self.found


def test_scanner_prefers_card_name_and_skips_picture_matching():
    from pokedex.recognizer.card_text import CardName

    recognizer = FakeRecognizer()
    scanner = Scanner(recognizer, FakeReader(CardName(1, 1.0, "Bulbasaur")))
    result = scanner.identify(Image.new("RGB", (10, 10)))
    assert [(m.pokemon_id, m.source) for m in result] == [(1, "card")]
    assert recognizer.calls == 0


def test_scanner_falls_back_to_picture():
    recognizer = FakeRecognizer()
    result = Scanner(recognizer, FakeReader(None)).identify(Image.new("RGB", (10, 10)))
    assert [(m.pokemon_id, m.source) for m in result] == [(25, "picture")]
    assert Scanner(recognizer).identify(Image.new("RGB", (10, 10)))[0].pokemon_id == 25
