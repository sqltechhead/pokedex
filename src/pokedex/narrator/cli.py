"""Command line entry point: ``uv run --extra narrate pokedex-narrate``.

Reads each stored Pokédex entry aloud with a Piper voice and saves it as
OGG audio for the UI to play after the cry. Runs offline once the voice is
downloaded, so generate on a PC and copy data/ to the Pi.

    pokedex-narrate                         # entries without narration yet
    pokedex-narrate --force                 # regenerate all (after changing voice)
    pokedex-narrate --voice en_GB-cori-high --force
    pokedex-narrate --clean                 # natural voice, no device effect
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pokedex.db import PokedexDB
from pokedex.paths import DEFAULT_DATA_DIR, DataPaths


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pokedex-narrate",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="data folder")
    parser.add_argument("--voice", default=None, help="Piper voice name (default en_US-ryan-high)")
    parser.add_argument(
        "--clean",
        dest="device",
        action="store_false",
        help="skip the device effect and use the voice as recorded",
    )
    parser.add_argument("--force", action="store_true", help="regenerate existing narration")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import soundfile

        from pokedex.narrator.effects import device_effect, finish
        from pokedex.narrator.script import narration_text
        from pokedex.narrator.voice import DEFAULT_VOICE, Speaker, ensure_voice
    except ImportError:
        print("Narration needs extra packages: uv sync --extra narrate", file=sys.stderr)
        return 1

    paths = DataPaths(args.data)
    if not paths.db.exists():
        print(f"No database at {paths.db}. Run `uv run pokedex-fetch` first.", file=sys.stderr)
        return 1
    paths.narration.mkdir(parents=True, exist_ok=True)
    speaker = Speaker(ensure_voice(args.voice or DEFAULT_VOICE, paths.voices), device=args.device)

    with PokedexDB(paths.db) as db:
        todo = [p for p in db.all() if args.force or not p.narration_path]
        if not todo:
            print("Narration: up to date.")
        for n, mon in enumerate(todo, 1):
            audio = speaker.speak(narration_text(mon))
            if args.device:
                audio = device_effect(audio, speaker.sample_rate)
            dest = paths.narration_file(mon.id)
            soundfile.write(
                dest,
                finish(audio, speaker.sample_rate),
                speaker.sample_rate,
                format="OGG",
                subtype="VORBIS",
            )
            db.set_narration_path(mon.id, paths.relative(dest))
            print(f"[{n}/{len(todo)}] #{mon.id:03d} {mon.name}")
    return 0
