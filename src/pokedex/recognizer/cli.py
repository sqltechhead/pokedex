"""Command line entry point: ``uv run --extra recognize pokedex-embed``.

Builds the reference vectors the scanner matches camera frames against:
one per Pokémon from text prompts and one from its official artwork. Re-run
after fetching more Pokémon. Downloads the CLIP model the first time.
"""

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from pokedex.db import PokedexDB
from pokedex.paths import DEFAULT_DATA_DIR, DataPaths


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pokedex-embed", description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="data folder")
    parser.add_argument("--model", default=None, help="CLIP model (default clip-vit-base-patch32)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        from pokedex.recognizer.clip import DEFAULT_MODEL, ImageEncoder, TextEncoder, ensure_model
        from pokedex.recognizer.references import build_references, references_path
    except ImportError:
        print("Recognition needs extra packages: uv sync --extra recognize", file=sys.stderr)
        return 1

    paths = DataPaths(args.data)
    if not paths.db.exists():
        print(f"No database at {paths.db}. Run `uv run pokedex-fetch` first.", file=sys.stderr)
        return 1
    model = args.model or DEFAULT_MODEL
    files = (
        "vision_model.onnx",
        "vision_model_quantized.onnx",
        "text_model.onnx",
        "tokenizer.json",
    )
    model_dir = ensure_model(model, paths.root / "models", files=files)

    with PokedexDB(paths.db) as db:
        pokemon = db.all()
    started = time.perf_counter()
    references = build_references(
        pokemon, paths, model, TextEncoder(model_dir), ImageEncoder(model_dir)
    )
    destination = references_path(paths, model)
    references.save(destination)
    elapsed = time.perf_counter() - started
    print(f"Built references for {len(pokemon)} Pokémon in {elapsed:.0f}s: {destination}")
    return 0
