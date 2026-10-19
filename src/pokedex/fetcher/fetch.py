"""Turn PokéAPI responses into :class:`Pokemon` records."""

from collections.abc import Sequence
from pathlib import Path

from pokedex.fetcher.api import PokeAPIClient, PokemonResponse, SpeciesResponse
from pokedex.models import BaseStats, Pokemon
from pokedex.paths import DataPaths

# Flavour text is chosen from the first of these games that has an English
# entry, falling back to the most recent English entry of any game.
DEFAULT_VERSIONS = ("red", "blue", "yellow", "crystal", "emerald", "platinum")

# PokéAPI stat name -> BaseStats field.
STAT_FIELDS = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}


def build_pokemon(
    mon: PokemonResponse,
    species: SpeciesResponse,
    *,
    versions: Sequence[str] = DEFAULT_VERSIONS,
    sprite_path: str | None = None,
    artwork_path: str | None = None,
    cry_path: str | None = None,
) -> Pokemon:
    types = mon.type_names
    stats = {STAT_FIELDS[s.stat.name]: s.base_stat for s in mon.stats if s.stat.name in STAT_FIELDS}
    return Pokemon(
        id=mon.id,
        name=species.english_name,
        genus=species.english_genus,
        type1=types[0],
        type2=types[1] if len(types) > 1 else None,
        height_dm=mon.height,
        weight_hg=mon.weight,
        stats=BaseStats(**stats),
        flavor_text=species.flavor_text(versions),
        sprite_path=sprite_path,
        artwork_path=artwork_path,
        cry_path=cry_path,
        evolution_chain_id=species.evolution_chain.id if species.evolution_chain else None,
    )


def fetch_pokemon(
    client: PokeAPIClient,
    pokemon_id: int,
    paths: DataPaths,
    *,
    versions: Sequence[str] = DEFAULT_VERSIONS,
    artwork: bool = True,
    cries: bool = True,
) -> Pokemon:
    """Fetch one Pokémon's data and download its images and cry into the data folder."""
    mon = client.pokemon(pokemon_id)
    species = client.species(pokemon_id)
    sprite_path = _download(client, mon.sprites.front_default, paths.sprite_file(pokemon_id), paths)
    artwork_path = (
        _download(client, mon.sprites.artwork_url, paths.artwork_file(pokemon_id), paths)
        if artwork
        else None
    )
    return build_pokemon(
        mon,
        species,
        versions=versions,
        sprite_path=sprite_path,
        artwork_path=artwork_path,
        cry_path=download_cry(client, mon, paths) if cries else None,
    )


def download_cry(client: PokeAPIClient, mon: PokemonResponse, paths: DataPaths) -> str | None:
    """Save the modern cry; returns its stored path, or None if PokéAPI has none."""
    return _download(client, mon.cries.latest, paths.cry_file(mon.id), paths)


def _download(client: PokeAPIClient, url: str | None, dest: Path, paths: DataPaths) -> str | None:
    if url is None:
        return None
    client.download(url, dest)
    return paths.relative(dest)
