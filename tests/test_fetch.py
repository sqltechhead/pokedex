import pytest
from pydantic import ValidationError

from pokedex.fetcher.api import PokemonResponse, SpeciesResponse, clean_text
from pokedex.fetcher.fetch import build_pokemon


def test_clean_text_removes_game_line_breaks():
    assert clean_text("A\nB\fC­D  E") == "A B CD E"


def test_species_prefers_requested_version(pikachu_species: SpeciesResponse):
    assert pikachu_species.flavor_text(["sword", "red"]).startswith("It keeps its tail")
    assert pikachu_species.flavor_text(["red"]).startswith("When several of these POKéMON gather")


def test_species_falls_back_to_newest_english_entry(pikachu_species: SpeciesResponse):
    assert pikachu_species.flavor_text(["gold"]).startswith("It keeps its tail")


def test_missing_required_field_is_rejected(pikachu_json: dict):
    del pikachu_json["stats"]
    with pytest.raises(ValidationError):
        PokemonResponse.model_validate(pikachu_json)


def test_build_pokemon(pikachu: PokemonResponse, pikachu_species: SpeciesResponse):
    mon = build_pokemon(pikachu, pikachu_species, sprite_path="sprites/0025.png")

    assert mon.name == "Pikachu"
    assert mon.genus == "Mouse Pokémon"
    assert mon.types == ("electric",)
    assert mon.height_m == pytest.approx(0.4)
    assert mon.stats.sp_attack == 50
    assert mon.stats.total == 320
    assert mon.sprite_path == "sprites/0025.png"
    assert mon.artwork_path is None


def test_artwork_url(pikachu: PokemonResponse):
    assert pikachu.sprites.artwork_url == "https://img/art/25.png"


def test_cry_url_and_path(pikachu_json: dict, pikachu_species: SpeciesResponse):
    pikachu_json["cries"] = {"latest": "https://cries/latest/25.ogg", "legacy": None}
    mon = PokemonResponse.model_validate(pikachu_json)
    assert mon.cries.latest == "https://cries/latest/25.ogg"
    assert build_pokemon(mon, pikachu_species, cry_path="cries/0025.ogg").cry_path == (
        "cries/0025.ogg"
    )


def test_cries_are_optional(pikachu: PokemonResponse):
    assert pikachu.cries.latest is None
