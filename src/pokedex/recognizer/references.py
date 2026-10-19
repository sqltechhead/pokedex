"""Per-Pokémon reference vectors, built once on a PC and loaded by the matcher."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from pokedex.models import Pokemon
from pokedex.paths import DataPaths
from pokedex.recognizer.clip import ImageEncoder, TextEncoder

# The kinds of thing the Pokédex gets pointed at. Each becomes one text
# prompt per Pokémon; their vectors are averaged.
PROMPTS = (
    "a photo of {name}, a Pokémon",
    "a photo of a {name} plush toy",
    "a photo of a {name} Pokémon trading card",
    "a photo of a {name} Pokémon figure",
    "{name}, the {genus}",
)


@dataclass(frozen=True)
class References:
    ids: np.ndarray
    """National Pokédex numbers, one per row."""
    text: np.ndarray
    """Unit vectors from the prompts."""
    image: np.ndarray
    """Unit vectors from the official artwork (zeros where it is missing)."""
    model: str

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, ids=self.ids, text=self.text, image=self.image, model=self.model)

    @classmethod
    def load(cls, path: Path) -> "References":
        data = np.load(path)
        return cls(data["ids"], data["text"], data["image"], str(data["model"]))


def references_path(paths: DataPaths, model: str) -> Path:
    return paths.root / "recognition" / f"{model}.npz"


def prompts_for(mon: Pokemon) -> list[str]:
    genus = mon.genus or "Pokémon"
    return [prompt.format(name=mon.name, genus=genus) for prompt in PROMPTS]


def build_references(
    pokemon: list[Pokemon],
    paths: DataPaths,
    model: str,
    text_encoder: TextEncoder,
    image_encoder: ImageEncoder,
    *,
    batch: int = 16,
) -> References:
    text = np.stack([text_encoder.encode(prompts_for(m)).mean(axis=0) for m in pokemon])
    text /= np.linalg.norm(text, axis=1, keepdims=True)

    image = np.zeros_like(text)
    with_art = [(i, m) for i, m in enumerate(pokemon) if m.artwork_path or m.sprite_path]
    for start in range(0, len(with_art), batch):
        chunk = with_art[start : start + batch]
        images = [_on_white(paths.resolve(m.artwork_path or m.sprite_path)) for _, m in chunk]
        # Average each image with its mirror so left/right-facing poses both match.
        vectors = image_encoder.encode(images) + image_encoder.encode(
            [ImageOps.mirror(img) for img in images]
        )
        for (row, _), vector in zip(chunk, vectors, strict=True):
            image[row] = vector / np.linalg.norm(vector)

    return References(np.array([m.id for m in pokemon]), text, image, model)


def _on_white(path: Path) -> Image.Image:
    """Artwork has a transparent background; CLIP expects an opaque image."""
    image = Image.open(path).convert("RGBA")
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, image).convert("RGB")
