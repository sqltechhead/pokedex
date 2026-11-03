"""The index and per-Pokémon entry files the Pico reads (see firmware/lib/dex/records.py)."""

import json
import unicodedata
from collections.abc import Iterable, Mapping

from pokedex.fetcher.fetch import TYPES
from pokedex.models import Ability, EvolutionChain, Move, Pokemon

TypeChart = Mapping[tuple[str, str], float]

# Game names for "Moves from …" on the device.
VERSION_NAMES = {
    "scarlet-violet": "Scarlet & Violet",
    "sword-shield": "Sword & Shield",
    "brilliant-diamond-shining-pearl": "Brilliant Diamond & Shining Pearl",
    "ultra-sun-ultra-moon": "Ultra Sun & Ultra Moon",
    "sun-moon": "Sun & Moon",
    "omega-ruby-alpha-sapphire": "Omega Ruby & Alpha Sapphire",
    "x-y": "X & Y",
    "black-2-white-2": "Black 2 & White 2",
    "black-white": "Black & White",
    "heartgold-soulsilver": "HeartGold & SoulSilver",
    "legends-za": "Legends: Z-A",
    "legends-arceus": "Legends: Arceus",
    "lets-go-pikachu-lets-go-eevee": "Let's Go",
}
MULTIPLIERS = (4.0, 2.0, 0.5, 0.25, 0.0)
"""Matchup groups written to each entry, as keys "4", "2", "0.5", "0.25", "0"."""


def search_key(name: str) -> str:
    """Lower-case ASCII letters and digits: "Mr. Mime" -> "mrmime", "Flabébé" -> "flabebe".

    Done here because CircuitPython has no unicodedata to strip accents.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if c.isascii() and c.isalnum()).lower()


def index_lines(pokemon: Iterable[Pokemon]) -> list[str]:
    """``id<TAB>name<TAB>search key<TAB>type1<TAB>type2<TAB>generation``, in Pokédex order."""
    return [
        "\t".join(
            (
                str(p.id),
                p.name,
                search_key(p.name),
                p.type1,
                p.type2 or "",
                str(p.generation or ""),
            )
        )
        for p in sorted(pokemon, key=lambda p: p.id)
    ]


def version_name(slug: str | None) -> str:
    if not slug:
        return ""
    return VERSION_NAMES.get(slug) or slug.replace("-", " ").title()


def matchups(types: Iterable[str], chart: TypeChart) -> dict[str, list[str]]:
    """Attacking types grouped by how much damage they do to a Pokémon of these types."""
    groups: dict[str, list[str]] = {f"{m:g}": [] for m in MULTIPLIERS}
    for attacker in TYPES:
        multiplier = 1.0
        for defender in types:
            multiplier *= chart.get((attacker, defender), 1.0)
        if multiplier != 1.0:
            groups[f"{multiplier:g}"].append(attacker)
    return groups


def entry(
    mon: Pokemon,
    chains: Mapping[int, EvolutionChain],
    moves: Mapping[int, Move] | None = None,
    abilities: Mapping[int, Ability] | None = None,
    chart: TypeChart | None = None,
) -> dict:
    stats = mon.stats
    chain = chains.get(mon.evolution_chain_id) if mon.evolution_chain_id else None
    return {
        "id": mon.id,
        "genus": mon.genus,
        "height_dm": mon.height_dm,
        "weight_hg": mon.weight_hg,
        "stats": [
            stats.hp,
            stats.attack,
            stats.defense,
            stats.sp_attack,
            stats.sp_defense,
            stats.speed,
        ],
        "flavor": mon.flavor_text,
        "chain": chain_dict(chain) if chain else None,
        "region": mon.generation,
        "abilities": [
            [abilities[a.ability_id].name, a.hidden, abilities[a.ability_id].description]
            for a in mon.abilities
            if abilities and a.ability_id in abilities
        ],
        "moves_from": version_name(mon.move_version),
        "moves": [
            [m.level, moves[m.move_id].name, moves[m.move_id].type, moves[m.move_id].power]
            for m in mon.level_moves
            if moves and m.move_id in moves
        ],
        "matchups": matchups(mon.types, chart) if chart else None,
    }


def chain_dict(chain: EvolutionChain) -> dict:
    return {
        "root": chain.root_id,
        "root_name": chain.root_name,
        "steps": [[e.from_id, e.to_id, e.to_name, e.method] for e in chain.evolutions],
    }


def entry_json(
    mon: Pokemon,
    chains: Mapping[int, EvolutionChain],
    moves: Mapping[int, Move] | None = None,
    abilities: Mapping[int, Ability] | None = None,
    chart: TypeChart | None = None,
) -> str:
    # ensure_ascii=False keeps "é" as itself; the Pico's json reads UTF-8 fine.
    data = entry(mon, chains, moves, abilities, chart)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
