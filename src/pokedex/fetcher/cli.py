"""Command line entry point: ``uv run pokedex-fetch``.

Fetches Pokémon, then fills in cries, evolution chains, regions, abilities,
level-up moves, shiny artwork, colours, shapes and the other browse
categories, and the type chart, for every Pokémon in the database.

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
from pokedex.fetcher.fetch import (
    DEFAULT_VERSIONS,
    TYPES,
    details,
    download_cry,
    download_shiny,
    fetch_pokemon,
    species_details,
)
from pokedex.models import Ability, Move
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
        failures += fetch_details(db, client, paths, args)
        failures += fetch_species_details(db, client, args)
        failures += fetch_moves_and_abilities(db, client, args)
        failures += fetch_type_chart(db, client, args)
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


def fetch_details(
    db: PokedexDB, client: PokeAPIClient, paths: DataPaths, args: argparse.Namespace
) -> list[str]:
    """Region, abilities, moves and shiny artwork for Pokémon stored before they existed."""
    todo = sorted(db.ids_without_details())
    failures = []
    for n, pid in enumerate(todo, 1):
        progress = f"[{n}/{len(todo)}] details #{pid:03d}"
        stored = db.get(pid)
        assert stored is not None
        try:
            mon = client.pokemon(pid)
            species = client.species(pid)
            shiny = download_shiny(client, mon, paths) if args.artwork else None
        except FETCH_ERRORS as exc:
            failures.append(f"details #{pid}")
            print(f"{progress} FAILED: {exc}", file=sys.stderr)
            continue
        updated = stored.model_copy(update={**details(mon, species), "shiny_artwork_path": shiny})
        db.set_details(updated)
        print(f"{progress} {stored.name}: {len(updated.level_moves)} moves")
        time.sleep(args.delay)
    return failures


def fetch_species_details(
    db: PokedexDB, client: PokeAPIClient, args: argparse.Namespace
) -> list[str]:
    """Colour, shape, habitat and the rest for Pokémon stored before they existed."""
    todo = sorted(db.ids_without_species_details())
    failures = []
    for n, pid in enumerate(todo, 1):
        progress = f"[{n}/{len(todo)}] species #{pid:03d}"
        stored = db.get(pid)
        assert stored is not None
        try:
            species = client.species(pid)
        except FETCH_ERRORS as exc:
            failures.append(f"species #{pid}")
            print(f"{progress} FAILED: {exc}", file=sys.stderr)
            continue
        db.set_species_details(stored.model_copy(update=species_details(species)))
        print(f"{progress} {stored.name}", flush=True)
        time.sleep(args.delay)
    return failures


def fetch_moves_and_abilities(
    db: PokedexDB, client: PokeAPIClient, args: argparse.Namespace
) -> list[str]:
    """Names, types and descriptions of every move and ability the Pokémon use."""
    failures = []
    moves, abilities = sorted(db.missing_move_ids()), sorted(db.missing_ability_ids())
    if not moves and not abilities:
        print("Moves and abilities: up to date.")
    for n, move_id in enumerate(moves, 1):
        try:
            r = client.move(move_id)
        except FETCH_ERRORS as exc:
            failures.append(f"move {move_id}")
            print(f"[{n}/{len(moves)}] move {move_id} FAILED: {exc}", file=sys.stderr)
            continue
        damage_class = r.damage_class.name if r.damage_class else None
        db.upsert_move(
            Move(
                id=r.id,
                name=r.english_name,
                type=r.type.name,
                power=r.power,
                damage_class=damage_class,
            )
        )
        print(f"[{n}/{len(moves)}] move {r.english_name}")
        time.sleep(args.delay)
    for n, ability_id in enumerate(abilities, 1):
        try:
            r = client.ability(ability_id)
        except FETCH_ERRORS as exc:
            failures.append(f"ability {ability_id}")
            print(f"[{n}/{len(abilities)}] ability {ability_id} FAILED: {exc}", file=sys.stderr)
            continue
        db.upsert_ability(Ability(id=r.id, name=r.english_name, description=r.description))
        print(f"[{n}/{len(abilities)}] ability {r.english_name}")
        time.sleep(args.delay)
    return failures


def fetch_type_chart(db: PokedexDB, client: PokeAPIClient, args: argparse.Namespace) -> list[str]:
    """The 18 × 18 type chart, one attacking type at a time."""
    todo = TYPES if args.refresh else [t for t in TYPES if t not in db.attacking_types()]
    if not todo:
        print("Type chart: up to date.")
    failures = []
    for name in todo:
        try:
            relations = client.type(name).damage_relations
        except FETCH_ERRORS as exc:
            failures.append(f"type {name}")
            print(f"Type {name} FAILED: {exc}", file=sys.stderr)
            continue
        effects = {t.name: 2.0 for t in relations.double_damage_to}
        effects.update({t.name: 0.5 for t in relations.half_damage_to})
        effects.update({t.name: 0.0 for t in relations.no_damage_to})
        db.set_type_effects(name, effects)
        print(f"Type {name}: {len(effects)} matchups")
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
