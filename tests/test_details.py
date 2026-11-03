"""Regions, abilities, level-up moves, the type chart and shiny pictures, PC side."""

import json
import wave

from PIL import Image

from pokedex.db import PokedexDB
from pokedex.fetcher.api import PokemonResponse, SpeciesResponse
from pokedex.fetcher.fetch import details, generation_number, level_up_moves
from pokedex.models import Ability, BaseStats, LevelMove, Move, Pokemon, PokemonAbility
from pokedex.sdcard import entries, images, sounds

STATS = BaseStats(hp=35, attack=55, defense=40, sp_attack=50, sp_defense=50, speed=90)


def _named(name: str, kind: str = "x", ident: int = 1) -> dict:
    return {"name": name, "url": f"https://pokeapi.co/api/v2/{kind}/{ident}/"}


def learn(level: int, group: str, group_id: int, method: str = "level-up") -> dict:
    return {
        "level_learned_at": level,
        "move_learn_method": _named(method),
        "version_group": _named(group, "version-group", group_id),
    }


def test_generation_numbers():
    assert [generation_number(f"generation-{n}") for n in ("i", "iv", "v", "viii", "ix")] == [
        1,
        4,
        5,
        8,
        9,
    ]


def test_moves_come_from_the_newest_main_game(pikachu_json: dict):
    pikachu_json["moves"] = [
        {
            "move": _named("thunder-shock", "move", 84),
            "version_group_details": [
                learn(1, "scarlet-violet", 25),
                learn(1, "blue-japan", 29),  # high id, but a 1996 game
                learn(0, "scarlet-violet", 25, method="machine"),
            ],
        },
        {
            "move": _named("quick-attack", "move", 98),
            "version_group_details": [learn(6, "scarlet-violet", 25), learn(13, "red-blue", 1)],
        },
    ]
    version, moves = level_up_moves(PokemonResponse.model_validate(pikachu_json))
    assert version == "scarlet-violet"
    assert moves == (LevelMove(level=1, move_id=84), LevelMove(level=6, move_id=98))


def test_details(pikachu_json: dict, pikachu_species_json: dict):
    pikachu_json["abilities"] = [
        {"ability": _named("lightning-rod", "ability", 31), "is_hidden": True, "slot": 3},
        {"ability": _named("static", "ability", 9), "is_hidden": False, "slot": 1},
    ]
    pikachu_species_json["generation"] = _named("generation-i")
    found = details(
        PokemonResponse.model_validate(pikachu_json),
        SpeciesResponse.model_validate(pikachu_species_json),
    )
    assert found["generation"] == 1
    assert found["abilities"] == (
        PokemonAbility(ability_id=9),
        PokemonAbility(ability_id=31, hidden=True),
    )
    assert found["move_version"] is None


def pikachu(**update) -> Pokemon:
    mon = Pokemon(
        id=25,
        name="Pikachu",
        type1="electric",
        height_dm=4,
        weight_hg=60,
        stats=STATS,
        generation=1,
        abilities=(PokemonAbility(ability_id=9), PokemonAbility(ability_id=31, hidden=True)),
        level_moves=(LevelMove(level=1, move_id=84), LevelMove(level=6, move_id=98)),
        move_version="scarlet-violet",
    )
    return mon.model_copy(update=update)


def test_database_round_trip_and_old_rows(tmp_path):
    with PokedexDB(tmp_path / "pokedex.db") as db:
        db.upsert(pikachu(generation=None, abilities=(), level_moves=(), move_version=None))
        assert db.ids_without_details() == {25}
        db.set_details(pikachu())
        assert db.get(25).model_copy(update={"fetched_at": None}) == pikachu()
        assert db.ids_without_details() == set()
        assert db.missing_move_ids() == {84, 98}
        assert db.missing_ability_ids() == {9, 31}
        db.upsert_move(Move(id=84, name="Thunder Shock", type="electric", power=40))
        db.upsert_ability(Ability(id=9, name="Static", description="May paralyse."))
        assert db.missing_move_ids() == {98}
        assert db.moves()[84].name == "Thunder Shock"
        db.set_type_effects("ground", {"electric": 2.0, "flying": 0.0})
        db.set_type_effects("ground", {"electric": 2.0, "flying": 0.0})  # replaces, no duplicates
        assert db.type_chart() == {("ground", "electric"): 2.0, ("ground", "flying"): 0.0}
        assert db.attacking_types() == {"ground"}


CHART = {
    ("ground", "electric"): 2.0,
    ("ground", "flying"): 0.0,
    ("electric", "flying"): 2.0,
    ("ice", "flying"): 2.0,
    ("rock", "flying"): 2.0,
    ("grass", "flying"): 0.5,
    ("grass", "electric"): 1.0,
    ("fighting", "flying"): 0.5,
    ("bug", "flying"): 0.5,
    ("steel", "electric"): 0.5,
    ("steel", "flying"): 0.5,
    ("electric", "electric"): 0.5,
}


def test_matchups_multiply_both_types():
    groups = entries.matchups(("electric", "flying"), CHART)  # e.g. Zapdos
    assert groups["0"] == ["ground"]  # 2 x 0
    assert groups["0.25"] == ["steel"]  # 0.5 x 0.5
    assert groups["2"] == ["rock", "ice"]
    assert set(groups["0.5"]) == {"fighting", "bug", "grass"}
    assert "electric" not in sum(groups.values(), [])  # 0.5 x 2 = normal damage
    assert groups["4"] == []


def test_entry_has_the_new_fields():
    moves = {
        84: Move(id=84, name="Thunder Shock", type="electric", power=40),
        98: Move(id=98, name="Quick Attack", type="normal", power=40),
    }
    abilities = {9: Ability(id=9, name="Static", description="May paralyse.")}
    data = json.loads(entries.entry_json(pikachu(), {}, moves, abilities, CHART))
    assert data["region"] == 1
    assert data["abilities"] == [["Static", False, "May paralyse."]]  # unknown ability skipped
    assert data["moves_from"] == "Scarlet & Violet"
    assert data["moves"] == [
        [1, "Thunder Shock", "electric", 40],
        [6, "Quick Attack", "normal", 40],
    ]
    assert data["matchups"]["2"] == ["ground"]
    line = entries.index_lines([pikachu()])[0]
    assert line.split("\t") == ["25", "Pikachu", "pikachu", "electric", "", "1"]


def test_silhouette(tmp_path):
    art = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    art.paste((250, 200, 30, 255), (50, 50, 150, 150))
    art.save(tmp_path / "a.png")
    images.silhouette(tmp_path / "a.png", tmp_path / "s.bmp", 160)
    out = Image.open(tmp_path / "s.bmp")
    assert out.size == (160, 160)
    indices = set(out.tobytes())
    assert indices == {0, 1}
    assert out.getpalette()[3:6] == list(images.SILHOUETTE)


def test_sounds(tmp_path):
    sounds.write_sounds(tmp_path)
    for name in ("startup", "correct", "wrong"):
        with wave.open(str(tmp_path / f"{name}.wav")) as w:
            assert (w.getnchannels(), w.getsampwidth()) == (1, 2)
            assert w.getframerate() == 22050
            assert 0.3 < w.getnframes() / 22050 < 2.0
    assert round(sounds.note("A4")) == 440 and round(sounds.note("C5")) == 523
