"""Identifying the Pokémon in a camera frame."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from pokedex.recognizer.clip import ImageEncoder
from pokedex.recognizer.references import References

TEXT_WEIGHT = 0.4
"""Share of the score from the text prompts; the rest is artwork similarity.

On fake photos (artwork on cluttered backgrounds) 0.25-0.5 did best and
either source alone was clearly worse. Real plushies look less like the
artwork than those, so this leans a little towards text.
"""
TEMPERATURE = 100.0
"""CLIP's own logit scale: turns similarities into confident probabilities."""


@dataclass(frozen=True)
class Match:
    pokemon_id: int
    score: float
    """Blended cosine similarity."""
    confidence: float
    """Share of probability among all Pokémon, 0..1."""
    source: Literal["picture", "card"] = "picture"
    """How it was recognised: CLIP picture matching or reading a card's name."""


class Recognizer:
    def __init__(
        self,
        model_dir: Path,
        references: References,
        *,
        quantized: bool = True,
        text_weight: float = TEXT_WEIGHT,
    ) -> None:
        self._encoder = ImageEncoder(model_dir, quantized=quantized)
        self.references = references
        self.text_weight = text_weight

    def identify(self, image: Image.Image, top: int = 3) -> list[Match]:
        return rank(self.references, self._encoder.encode([image])[0], self.text_weight, top)


def rank(references: References, query: np.ndarray, text_weight: float, top: int) -> list[Match]:
    scores = text_weight * (references.text @ query) + (1 - text_weight) * (
        references.image @ query
    )
    logits = TEMPERATURE * (scores - scores.max())
    probabilities = np.exp(logits) / np.exp(logits).sum()
    best = np.argsort(-scores)[:top]
    return [Match(int(references.ids[i]), float(scores[i]), float(probabilities[i])) for i in best]
