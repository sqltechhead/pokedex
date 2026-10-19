"""The scanner: reads a card's printed name, or else recognises the picture."""

from collections.abc import Iterable
from pathlib import Path

from PIL import Image

from pokedex.paths import DataPaths
from pokedex.recognizer.card_text import CardReader
from pokedex.recognizer.card_text import ensure_models as ensure_card_models
from pokedex.recognizer.clip import DEFAULT_MODEL
from pokedex.recognizer.matcher import Match, Recognizer
from pokedex.recognizer.references import References, references_path


class Scanner:
    def __init__(self, recognizer: Recognizer, card_reader: CardReader | None = None) -> None:
        self.recognizer = recognizer
        self.card_reader = card_reader

    def identify(self, image: Image.Image, top: int = 3) -> list[Match]:
        """Best guesses, most likely first.

        A readable card name is near-certain, so it is returned alone and the
        slower picture matching is skipped; plushies and figures have no name
        to read and fall through to it.
        """
        if self.card_reader is not None:
            card = self.card_reader.find_name(image)
            if card is not None:
                return [Match(card.pokemon_id, card.similarity, 1.0, source="card")]
        return self.recognizer.identify(image, top)


def load_scanner(
    paths: DataPaths,
    names: Iterable[tuple[int, str]],
    *,
    model: str = DEFAULT_MODEL,
    quantized: bool = True,
    read_cards: bool = True,
) -> Scanner:
    """Build a scanner from the data folder; raises FileNotFoundError without references."""
    refs_file = references_path(paths, model)
    if not refs_file.exists():
        raise FileNotFoundError(
            f"No references at {refs_file}. Run `uv run --extra recognize pokedex-embed`."
        )
    models_dir: Path = paths.root / "models"
    recognizer = Recognizer(models_dir / model, References.load(refs_file), quantized=quantized)
    reader = CardReader(ensure_card_models(models_dir), names) if read_cards else None
    return Scanner(recognizer, reader)
