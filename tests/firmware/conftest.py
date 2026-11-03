"""Fixtures for the firmware's pure-logic modules (firmware/lib/dex), run on the PC."""

import pytest

from dex.index import Dex
from dex.state import PokedexState

ENTRIES = (
    (1, "Bulbasaur", "bulbasaur", "grass", "poison"),
    (4, "Charmander", "charmander", "fire", None),
    (5, "Charmeleon", "charmeleon", "fire", None),
    (6, "Charizard", "charizard", "fire", "flying"),
    (7, "Squirtle", "squirtle", "water", None),
    (25, "Pikachu", "pikachu", "electric", None),
    (29, "Nidoran♀", "nidoran", "poison", None),
    (122, "Mr. Mime", "mrmime", "psychic", "fairy"),
    (133, "Eevee", "eevee", "normal", None),
    (669, "Flabébé", "flabebe", "fairy", None),
)

CHARMANDER_CHAIN = {
    "root": 4,
    "root_name": "Charmander",
    "steps": [[4, 5, "Charmeleon", "Lv. 16"], [5, 6, "Charizard", "Lv. 36"]],
}
# Eevee's branches, of which only Eevee itself is in ENTRIES.
EEVEE_CHAIN = {
    "root": 133,
    "root_name": "Eevee",
    "steps": [[133, 134, "Vaporeon", "Water Stone"], [133, 135, "Jolteon", "Thunder Stone"]],
}


def entry(pokemon_id: int) -> dict | None:
    """Stands in for Records.entry: what the SD card would hold."""
    chains = {4: CHARMANDER_CHAIN, 5: CHARMANDER_CHAIN, 6: CHARMANDER_CHAIN, 133: EEVEE_CHAIN}
    return {
        "id": pokemon_id,
        "genus": "Test Pokémon",
        "height_dm": 6,
        "weight_hg": 85,
        "stats": [39, 52, 43, 60, 50, 65],
        "flavor": "A test entry.",
        "chain": chains.get(pokemon_id),
    }


@pytest.fixture
def dex() -> Dex:
    return Dex(ENTRIES)


@pytest.fixture
def state(dex: Dex) -> PokedexState:
    return PokedexState(dex, entry)


def ids(dex: Dex, positions: list[int]) -> list[int]:
    return [dex.ids[pos] for pos in positions]
