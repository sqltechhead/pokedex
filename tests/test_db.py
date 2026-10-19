import sqlite3

from pokedex.db import PokedexDB
from pokedex.models import BaseStats, Pokemon


def make_pokemon(pid: int = 25, **overrides) -> Pokemon:
    fields = {
        "id": pid,
        "name": "Pikachu",
        "genus": "Mouse Pokémon",
        "type1": "electric",
        "height_dm": 4,
        "weight_hg": 60,
        "stats": BaseStats(hp=35, attack=55, defense=40, sp_attack=50, sp_defense=50, speed=90),
        "flavor_text": "Electric mouse.",
        "sprite_path": "sprites/0025.png",
        "artwork_path": "artwork/0025.png",
    }
    return Pokemon(**(fields | overrides))


def test_round_trip(tmp_path):
    with PokedexDB(tmp_path / "pokedex.db") as db:
        db.upsert(make_pokemon())
        stored = db.get(25)

    assert stored is not None
    assert stored.model_dump(exclude={"fetched_at"}) == make_pokemon().model_dump(
        exclude={"fetched_at"}
    )
    assert stored.fetched_at is not None


def test_queries(tmp_path):
    with PokedexDB(tmp_path / "pokedex.db") as db:
        db.upsert(make_pokemon(25))
        db.upsert(
            make_pokemon(6, name="Charizard", type1="fire", type2="flying", artwork_path=None)
        )

        assert db.count() == 2
        assert [p.id for p in db.all()] == [6, 25]
        assert [p.name for p in db.by_type("flying")] == ["Charizard"]
        assert db.ids() == {6, 25}
        assert db.ids(with_artwork=True) == {25}
        assert db.get(999) is None


def test_upgrades_database_without_artwork_column(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE pokemon (id INTEGER PRIMARY KEY, name TEXT NOT NULL, type1 TEXT, type2 TEXT)"
    )
    con.close()

    with PokedexDB(path):
        pass

    con = sqlite3.connect(path)
    columns = {row[1] for row in con.execute("PRAGMA table_info(pokemon)")}
    con.close()
    assert "artwork_path" in columns
