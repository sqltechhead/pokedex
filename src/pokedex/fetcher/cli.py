"""Command line entry point: ``uv run pokedex-fetch``.

Fetches Pokémon, then fills in cries and evolution chains for every
Pokémon in the database.

    pokedex-fetch                  # Gen 1 (1-151)
    pokedex-fetch --last 1025      # every Pokémon
    pokedex-fetch --refresh        # re-fetch rows you already have
    pokedex-fetch --no-artwork     # pixel sprites only (smaller)
    pokedex-fetch --no-cries       # skip the cry audio

Re-running is safe: complete rows are skipped unless --refresh is passed, so
an interrupted run picks up where it stopped. Rows from an older run that
lack HD artwork are filled in automatically.
"""

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import requests
from pydantic import ValidationError

from pokedex.db import PokedexDB
from pokedex.fetcher.api import PokeAPIClient
from pokedex.fetcher.evolution import build_chain
from pokedex.fetcher.fetch import DEFAULT_VERSIONS, download_cry, fetch_pokemon
from pokedex.paths import DEFAULT_DATA_DIR, DataPaths

FETCH_ERRORS = (requests.RequestException, ValidationError)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pokedex-fetch",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--first", type=int, default=1, help="first National Pokédex number")
    parser.add_argument("--last", type=int, default=151, help="last National Pokédex number")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="data folder")
    parser.add_argument("--refresh", action="store_true", help="re-fetch existing rows")
    parser.add_argument(
        "--no-artwork",
        dest="artwork",
        action="store_false",
        help="skip the 475x475 official artwork (about 150 KB each)",
    )
    parser.add_argument(
        "--no-cries",
        dest="cries",
        action="store_false",
        help="skip each Pokémon's cry (about 10 KB each)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.2, help="seconds between Pokémon (be kind to the free API)"
    )
    parser.add_argument(
        "--versions",
        type=_csv,
        default=list(DEFAULT_VERSIONS),
        help="preferred games for flavour text, comma-separated",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = DataPaths(args.data)
    paths.sprites.mkdir(parents=True, exist_ok=True)
    if args.artwork:
        paths.artwork.mkdir(parents=True, exist_ok=True)
    if args.cries:
        paths.cries.mkdir(parents=True, exist_ok=True)

    with PokedexDB(paths.db) as db, PokeAPIClient() as client:
        failures = fetch_all_pokemon(db, client, paths, args)
        if args.cries:
            failures += fetch_cries(db, client, paths, args)
        failures += fetch_evolutions(db, client, args)
        print(f"\nDone. {db.count()} Pokémon in {paths.db}")

    if failures:
        print(f"Failed (just re-run to retry): {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


def fetch_all_pokemon(
    db: PokedexDB, client: PokeAPIClient, paths: DataPaths, args: argparse.Namespace
) -> list[str]:
    have = set() if args.refresh else db.ids(with_artwork=args.artwork)
    todo = [pid for pid in range(args.first, args.last + 1) if pid not in have]
    if not todo:
        print("Pokémon: already have that range.")
        return []

    failures = []
    for n, pid in enumerate(todo, 1):
        progress = f"[{n}/{len(todo)}] #{pid:03d}"
        try:
            pokemon = fetch_pokemon(
                client, pid, paths, versions=args.versions, artwork=args.artwork, cries=args.cries
            )
        except FETCH_ERRORS as exc:
            failures.append(f"#{pid}")
            print(f"{progress} FAILED: {exc}", file=sys.stderr)
            continue
        db.upsert(pokemon)
        print(f"{progress} {pokemon.name}")
        time.sleep(args.delay)
    return failures


def fetch_cries(
    db: PokedexDB, client: PokeAPIClient, paths: DataPaths, args: argparse.Namespace
) -> list[str]:
    """Download cries for Pokémon stored before cries were fetched."""
    todo = sorted(db.ids_without_cry())
    failures = []
    for n, pid in enumerate(todo, 1):
        progress = f"[{n}/{len(todo)}] cry #{pid:03d}"
        try:
            cry_path = download_cry(client, client.pokemon(pid), paths)
        except FETCH_ERRORS as exc:
            failures.append(f"cry #{pid}")
            print(f"{progress} FAILED: {exc}", file=sys.stderr)
            continue
        db.set_cry_path(pid, cry_path)
        print(f"{progress} {'saved' if cry_path else 'none available'}")
        time.sleep(args.delay)
    return failures


def fetch_evolutions(db: PokedexDB, client: PokeAPIClient, args: argparse.Namespace) -> list[str]:
    """Fetch the evolution chain of every stored Pokémon that lacks one.

    Rows saved before evolution data existed only need their species
    re-fetched to learn their chain, not their images.
    """
    failures = []
    for pid in sorted(db.ids_without_chain()):
        try:
            species = client.species(pid)
        except FETCH_ERRORS as exc:
            failures.append(f"species #{pid}")
            print(f"Species #{pid:03d} FAILED: {exc}", file=sys.stderr)
            continue
        db.set_evolution_chain_id(
            pid, species.evolution_chain.id if species.evolution_chain else None
        )
        print(f"Linked #{pid:03d} to its evolution chain")
        time.sleep(args.delay)

    todo = sorted(db.chain_ids_to_fetch(refresh=args.refresh))
    if not todo:
        print("Evolution chains: up to date.")
    for n, chain_id in enumerate(todo, 1):
        progress = f"[{n}/{len(todo)}] chain {chain_id}"
        try:
            chain = build_chain(client.evolution_chain(chain_id))
        except FETCH_ERRORS as exc:
            failures.append(f"chain {chain_id}")
            print(f"{progress} FAILED: {exc}", file=sys.stderr)
            continue
        db.upsert_chain(chain)
        names = " → ".join(
            "/".join(chain.name(species_id) for species_id in stage) for stage in chain.stages()
        )
        print(f"{progress} {names}")
        time.sleep(args.delay)
    return failures
