"""The index and per-Pokémon entry files the Pico reads (see firmware/lib/dex/records.py)."""

import json
import unicodedata
from collections.abc import Iterable, Mapping

from pokedex.models import EvolutionChain, Pokemon


def search_key(name: str) -> str:
    """Lower-case ASCII letters and digits: "Mr. Mime" -> "mrmime", "Flabébé" -> "flabebe".

    Done here because CircuitPython has no unicodedata to strip accents.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if c.isascii() and c.isalnum()).lower()


def index_lines(pokemon: Iterable[Pokemon]) -> list[str]:
    """``id<TAB>name<TAB>search key<TAB>type1<TAB>type2``, in Pokédex order."""
    return [
        "\t".join((str(p.id), p.name, search_key(p.name), p.type1, p.type2 or ""))
        for p in sorted(pokemon, key=lambda p: p.id)
    ]


def entry(mon: Pokemon, chains: Mapping[int, EvolutionChain]) -> dict:
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
    }


def chain_dict(chain: EvolutionChain) -> dict:
    return {
        "root": chain.root_id,
        "root_name": chain.root_name,
        "steps": [[e.from_id, e.to_id, e.to_name, e.method] for e in chain.evolutions],
    }


def entry_json(mon: Pokemon, chains: Mapping[int, EvolutionChain]) -> str:
    # ensure_ascii=False keeps "é" as itself; the Pico's json reads UTF-8 fine.
    return json.dumps(entry(mon, chains), ensure_ascii=False, separators=(",", ":"))
