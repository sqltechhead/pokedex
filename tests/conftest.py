import pytest

from pokedex.fetcher.api import PokemonResponse, SpeciesResponse


def _named(name: str) -> dict:
    return {"name": name, "url": f"https://pokeapi.co/api/v2/x/{name}/"}


@pytest.fixture
def pikachu_json() -> dict:
    """Trimmed /pokemon/25 response; real ones carry many more fields."""
    stats = {
        "hp": 35,
        "attack": 55,
        "defense": 40,
        "special-attack": 50,
        "special-defense": 50,
        "speed": 90,
    }
    return {
        "id": 25,
        "name": "pikachu",
        "height": 4,
        "weight": 60,
        "base_experience": 112,
        "types": [{"slot": 1, "type": _named("electric")}],
        "stats": [{"base_stat": v, "effort": 0, "stat": _named(k)} for k, v in stats.items()],
        "sprites": {
            "front_default": "https://img/sprite/25.png",
            "other": {"official-artwork": {"front_default": "https://img/art/25.png"}},
        },
    }


@pytest.fixture
def pikachu_species_json() -> dict:
    return {
        "id": 25,
        "name": "pikachu",
        "names": [
            {"name": "ピカチュウ", "language": _named("ja")},
            {"name": "Pikachu", "language": _named("en")},
        ],
        "genera": [{"genus": "Mouse Pokémon", "language": _named("en")}],
        "flavor_text_entries": [
            {
                "flavor_text": "When several of\nthese POKéMON\fgather, their\nelectricity could\nbuild and cause\nlightning storms.",  # noqa: E501
                "language": _named("en"),
                "version": _named("red"),
            },
            {
                "flavor_text": "It keeps its tail raised to monitor its surroundings.",
                "language": _named("en"),
                "version": _named("sword"),
            },
        ],
    }


@pytest.fixture
def pikachu(pikachu_json: dict) -> PokemonResponse:
    return PokemonResponse.model_validate(pikachu_json)


@pytest.fixture
def pikachu_species(pikachu_species_json: dict) -> SpeciesResponse:
    return SpeciesResponse.model_validate(pikachu_species_json)
