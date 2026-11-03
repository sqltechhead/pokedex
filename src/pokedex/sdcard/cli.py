"""Command line entry point: ``uv run pokedex-sdcard``.

Turns data/ (from pokedex-fetch and pokedex-narrate) into the files the
Pico 2 reads from its microSD card: a text index, one small JSON file per
entry, 8-bit BMP pictures, WAV sounds and bitmap fonts.

    pokedex-sdcard                         # build into build/sd/
    pokedex-sdcard --out /Volumes/POKEDEX  # straight onto a mounted card
    pokedex-sdcard --force                 # redo pictures and sounds too

Pictures and sounds already built are skipped, so a re-run after fetching
more Pokémon only converts the new ones. The index, entries and fonts are
always rewritten (they take seconds).
"""

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pokedex.db import PokedexDB
from pokedex.models import Pokemon
from pokedex.paths import DEFAULT_DATA_DIR, DataPaths
from pokedex.sdcard import audio, entries, fonts, images

DEFAULT_OUT = Path("build/sd")
FIRMWARE_DIR = Path(__file__).parents[3] / "firmware"
"""Scanned for the labels and button hints the fonts must cover."""

# Picture sizes in pixels; the screens in firmware/lib/dex/screens.py are laid out for these.
ART_BOX = 160  # entry screen
PREVIEW_BOX = 112  # list preview
EVOLUTION_BOXES = (72, 44, 26)  # evolution cards: big, three-way branches, Eevee's rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pokedex-sdcard",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="data folder")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="card folder to write (default build/sd)"
    )
    parser.add_argument("--force", action="store_true", help="rebuild existing pictures and sounds")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = DataPaths(args.data)
    if not paths.db.exists():
        print(f"No database at {paths.db}. Run `uv run pokedex-fetch` first.", file=sys.stderr)
        return 1
    with PokedexDB(paths.db) as db:
        pokemon = db.all()
        chains = db.chains()
    root = args.out / "pokedex"

    write_entries(root, pokemon, chains)
    write_fonts(root, pokemon)
    failures = write_media(root, paths, pokemon, force=args.force)
    print(f"\nDone: {len(pokemon)} Pokémon in {root}")
    print("Copy the pokedex/ folder to the root of a FAT32 microSD card.")
    if failures:
        print(f"Failed (re-run to retry): {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


def write_entries(root: Path, pokemon: list[Pokemon], chains: dict) -> None:
    (root / "mon").mkdir(parents=True, exist_ok=True)
    (root / "index.tsv").write_text("\n".join(entries.index_lines(pokemon)) + "\n", "utf-8")
    for mon in pokemon:
        (root / "mon" / f"{mon.id:04d}.json").write_text(entries.entry_json(mon, chains), "utf-8")
    print(f"Index and entries: {len(pokemon)} written")


def write_fonts(root: Path, pokemon: list[Pokemon]) -> None:
    texts = [f"{p.name} {p.genus or ''} {p.flavor_text}" for p in pokemon]
    texts += [path.read_text("utf-8") for path in sorted(FIRMWARE_DIR.rglob("*.py"))]
    chars = fonts.charset(*texts)
    for spec in fonts.FONTS:
        fonts.write_bdf(spec, chars, root / "fonts" / spec.filename)
    print(f"Fonts: {len(fonts.FONTS)} sizes, {len(chars)} characters each")


def write_media(root: Path, paths: DataPaths, pokemon: list[Pokemon], *, force: bool) -> list[str]:
    """Convert pictures and sounds; returns what failed."""
    ffmpeg = audio.ffmpeg_exe()
    jobs: list[tuple[str, Path | None, Path, Callable[[Path, Path], None]]] = []
    for mon in pokemon:
        sprite = _stored(paths, mon.sprite_path)
        hd_artwork = _stored(paths, mon.artwork_path)
        artwork = hd_artwork or sprite
        name = f"{mon.id:04d}"
        jobs += [
            ("art", artwork, root / "art" / f"{name}.bmp", _picture(ART_BOX)),
            # Artwork shrinks smoothly to any size. Game sprites only look right
            # enlarged by whole numbers, which made small ones (Bulbasaur) blocky
            # next to their neighbours, so they're only the fallback.
            (
                "preview",
                artwork,
                root / "spr" / f"{name}.bmp",
                _picture(PREVIEW_BOX, pixel_art=hd_artwork is None),
            ),
            *(
                ("evolution", artwork, root / f"ev{box}" / f"{name}.bmp", _picture(box))
                for box in EVOLUTION_BOXES
            ),
            ("cry", _stored(paths, mon.cry_path), root / "cry" / f"{name}.wav", _sound(ffmpeg)),
            (
                "narration",
                _stored(paths, mon.narration_path),
                root / "say" / f"{name}.wav",
                _sound(ffmpeg),
            ),
        ]
    todo = [job for job in jobs if job[1] and (force or not job[2].exists())]
    if not todo:
        print("Pictures and sounds: up to date.")
    failures = []
    for n, (kind, source, dest, convert) in enumerate(todo, 1):
        assert source is not None
        try:
            convert(source, dest)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            failures.append(f"{kind} {dest.stem}")
            print(f"[{n}/{len(todo)}] {kind} {dest.stem} FAILED: {exc}", file=sys.stderr)
            continue
        if n % 100 == 0 or n == len(todo):
            print(f"[{n}/{len(todo)}] pictures and sounds")
    return failures


def _stored(paths: DataPaths, stored: str | None) -> Path | None:
    if not stored:
        return None
    path = paths.resolve(stored)
    return path if path.exists() else None


def _picture(box: int, pixel_art: bool = False) -> Callable[[Path, Path], None]:
    return lambda source, dest: images.to_bmp(source, dest, box, pixel_art=pixel_art)


def _sound(ffmpeg: str) -> Callable[[Path, Path], None]:
    return lambda source, dest: audio.to_wav(source, dest, ffmpeg)
