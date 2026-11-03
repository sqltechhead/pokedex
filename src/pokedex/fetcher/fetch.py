"""Turn PokéAPI responses into :class:`Pokemon` records."""

from collections.abc import Sequence
from pathlib import Path

from pokedex.fetcher.api import PokeAPIClient, PokemonResponse, SpeciesResponse
from pokedex.models import BaseStats, LevelMove, Pokemon, PokemonAbility
from pokedex.paths import DataPaths

# Flavour text is chosen from the first of these games that has an English
# entry, falling back to the most recent English entry of any game.
DEFAULT_VERSIONS = ("red", "blue", "yellow", "crystal", "emerald", "platinum")

# The 18 types, in PokéAPI's order (it also has "stellar", "unknown" and "shadow").
TYPES = (
    "normal",
    "fighting",
    "flying",
    "poison",
    "ground",
    "rock",
    "bug",
    "ghost",
    "steel",
    "fire",
    "water",
    "grass",
    "electric",
    "psychic",
    "ice",
    "dragon",
    "dark",
    "fairy",
)

ROMAN = {"i": 1, "v": 5, "x": 10}

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
    shiny_artwork_path: str | None = None,
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
        **details(mon, species),
        **species_details(species),
        shiny_artwork_path=shiny_artwork_path,
    )


def species_details(species: SpeciesResponse) -> dict[str, object]:
    """Colour, shape, habitat, legendary/mythical/baby and egg groups, as Pokemon fields."""
    return {
        "color": species.color.name if species.color else None,
        "shape": species.shape.name if species.shape else None,
        "habitat": species.habitat.name if species.habitat else None,
        "legendary": species.is_legendary,
        "mythical": species.is_mythical,
        "baby": species.is_baby,
        "egg_groups": tuple(g.name for g in species.egg_groups),
    }


def details(mon: PokemonResponse, species: SpeciesResponse) -> dict[str, object]:
    """Region, abilities and level-up moves, as Pokemon fields."""
    version, moves = level_up_moves(mon)
    return {
        "generation": generation_number(species.generation.name) if species.generation else None,
        "abilities": tuple(
            PokemonAbility(ability_id=a.ability.id, hidden=a.is_hidden)
            for a in sorted(mon.abilities, key=lambda a: a.slot)
        ),
        "level_moves": moves,
        "move_version": version,
    }


def generation_number(name: str) -> int:
    """ "generation-iv" -> 4."""
    numeral = name.rsplit("-", 1)[-1]
    values = [ROMAN[c] for c in numeral]
    return sum(-v if v < nxt else v for v, nxt in zip(values, values[1:] + [0], strict=True))


# Main-series games, newest first: a Pokémon's moves come from the first one it's in.
# PokéAPI's version group ids follow the order it added them (Japan-only Red/Green
# and Blue came late), not release order, so the order is spelled out here.
MOVE_VERSIONS = (
    "scarlet-violet",
    "sword-shield",
    "brilliant-diamond-shining-pearl",
    "ultra-sun-ultra-moon",
    "sun-moon",
    "omega-ruby-alpha-sapphire",
    "x-y",
    "black-2-white-2",
    "black-white",
    "heartgold-soulsilver",
    "platinum",
    "diamond-pearl",
    "firered-leafgreen",
    "emerald",
    "ruby-sapphire",
    "crystal",
    "gold-silver",
    "yellow",
    "red-blue",
    # Spin-offs and side games, only for Pokémon in none of the above.
    "legends-za",
    "legends-arceus",
    "lets-go-pikachu-lets-go-eevee",
)


def level_up_moves(mon: PokemonResponse) -> tuple[str | None, tuple[LevelMove, ...]]:
    """Moves learned by levelling up, from the newest main game that has them."""
    by_group: dict[str, set[tuple[int, int]]] = {}
    for slot in mon.moves:
        for detail in slot.version_group_details:
            if detail.move_learn_method.name == "level-up":
                by_group.setdefault(detail.version_group.name, set()).add(
                    (detail.level_learned_at, slot.move.id)
                )
    if not by_group:
        return None, ()
    ranked = sorted(
        by_group, key=lambda g: MOVE_VERSIONS.index(g) if g in MOVE_VERSIONS else len(MOVE_VERSIONS)
    )
    name = ranked[0]
    return name, tuple(LevelMove(level=lv, move_id=mid) for lv, mid in sorted(by_group[name]))


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
    shiny_path = download_shiny(client, mon, paths) if artwork else None
    return build_pokemon(
        mon,
        species,
        versions=versions,
        sprite_path=sprite_path,
        artwork_path=artwork_path,
        shiny_artwork_path=shiny_path,
        cry_path=download_cry(client, mon, paths) if cries else None,
    )


def download_shiny(client: PokeAPIClient, mon: PokemonResponse, paths: DataPaths) -> str | None:
    paths.shiny_artwork.mkdir(parents=True, exist_ok=True)
    return _download(client, mon.sprites.shiny_artwork_url, paths.shiny_file(mon.id), paths)


def download_cry(client: PokeAPIClient, mon: PokemonResponse, paths: DataPaths) -> str | None:
    """Save the modern cry; returns its stored path, or None if PokéAPI has none."""
    return _download(client, mon.cries.latest, paths.cry_file(mon.id), paths)


def _download(client: PokeAPIClient, url: str | None, dest: Path, paths: DataPaths) -> str | None:
    if url is None:
        return None
    client.download(url, dest)
    return paths.relative(dest)
