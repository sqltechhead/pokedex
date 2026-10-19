"""SQLite storage for Pokémon records and evolution chains."""

import sqlite3
from collections import defaultdict
from pathlib import Path
from types import TracebackType
from typing import Self

from pokedex.models import BaseStats, Evolution, EvolutionChain, Pokemon

SCHEMA = """
CREATE TABLE IF NOT EXISTS pokemon (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    genus        TEXT,
    type1        TEXT NOT NULL,
    type2        TEXT,
    height_dm    INTEGER,
    weight_hg    INTEGER,
    hp           INTEGER,
    attack       INTEGER,
    defense      INTEGER,
    sp_attack    INTEGER,
    sp_defense   INTEGER,
    speed        INTEGER,
    flavor_text  TEXT,
    sprite_path  TEXT,
    artwork_path TEXT,
    cry_path     TEXT,
    narration_path TEXT,
    evolution_chain_id INTEGER,
    fetched_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_pokemon_type1 ON pokemon(type1);
CREATE INDEX IF NOT EXISTS ix_pokemon_type2 ON pokemon(type2);

-- One row per chain fetched, including chains with no evolutions (e.g. Tauros).
CREATE TABLE IF NOT EXISTS evolution_chain (
    id        INTEGER PRIMARY KEY,
    root_id   INTEGER NOT NULL,
    root_name TEXT NOT NULL
);

-- One row per evolution step. Species may be missing from the pokemon table
-- (e.g. Pichu when only Gen 1 was fetched), so names are kept here too.
CREATE TABLE IF NOT EXISTS evolution (
    chain_id  INTEGER NOT NULL REFERENCES evolution_chain(id),
    position  INTEGER NOT NULL,
    from_id   INTEGER NOT NULL,
    to_id     INTEGER NOT NULL,
    to_name   TEXT NOT NULL,
    method    TEXT NOT NULL,
    PRIMARY KEY (chain_id, position)
);
"""

# Columns added after the first release; ALTER TABLE brings old databases up to date.
MIGRATIONS = {
    "artwork_path": "TEXT",
    "evolution_chain_id": "INTEGER",
    "cry_path": "TEXT",
    "narration_path": "TEXT",
}

STAT_COLUMNS = tuple(BaseStats.model_fields)


class PokedexDB:
    """The ``pokemon`` table, read and written as :class:`Pokemon` objects."""

    def __init__(self, path: Path | str) -> None:
        self._con = sqlite3.connect(path)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(SCHEMA)
        self._migrate()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._con.close()

    def _migrate(self) -> None:
        have = {row["name"] for row in self._con.execute("PRAGMA table_info(pokemon)")}
        with self._con:
            for column, decl in MIGRATIONS.items():
                if column not in have:
                    self._con.execute(f"ALTER TABLE pokemon ADD COLUMN {column} {decl}")

    def upsert(self, pokemon: Pokemon) -> None:
        """Insert or replace one Pokémon; ``fetched_at`` is set to now."""
        row = _to_row(pokemon)
        columns = ", ".join(row)
        params = ", ".join(f":{key}" for key in row)
        with self._con:
            self._con.execute(f"INSERT OR REPLACE INTO pokemon ({columns}) VALUES ({params})", row)

    def get(self, pokemon_id: int) -> Pokemon | None:
        row = self._con.execute("SELECT * FROM pokemon WHERE id = ?", (pokemon_id,)).fetchone()
        return _from_row(row) if row else None

    def all(self) -> list[Pokemon]:
        return [_from_row(row) for row in self._con.execute("SELECT * FROM pokemon ORDER BY id")]

    def by_type(self, type_name: str) -> list[Pokemon]:
        rows = self._con.execute(
            "SELECT * FROM pokemon WHERE type1 = :t OR type2 = :t ORDER BY id", {"t": type_name}
        )
        return [_from_row(row) for row in rows]

    def ids(self, *, with_artwork: bool = False) -> set[int]:
        """IDs already stored; with_artwork limits it to rows that have HD artwork."""
        query = "SELECT id FROM pokemon"
        if with_artwork:
            query += " WHERE artwork_path IS NOT NULL"
        return {row["id"] for row in self._con.execute(query)}

    def count(self) -> int:
        return self._con.execute("SELECT COUNT(*) FROM pokemon").fetchone()[0]

    def ids_without_cry(self) -> set[int]:
        """Pokémon stored before cries were downloaded."""
        return {
            row["id"] for row in self._con.execute("SELECT id FROM pokemon WHERE cry_path IS NULL")
        }

    def set_cry_path(self, pokemon_id: int, cry_path: str | None) -> None:
        with self._con:
            self._con.execute(
                "UPDATE pokemon SET cry_path = ? WHERE id = ?", (cry_path, pokemon_id)
            )

    def set_narration_path(self, pokemon_id: int, narration_path: str | None) -> None:
        with self._con:
            self._con.execute(
                "UPDATE pokemon SET narration_path = ? WHERE id = ?", (narration_path, pokemon_id)
            )

    # Evolution chains

    def ids_without_chain(self) -> set[int]:
        """Pokémon stored before evolution data existed."""
        rows = self._con.execute("SELECT id FROM pokemon WHERE evolution_chain_id IS NULL")
        return {row["id"] for row in rows}

    def set_evolution_chain_id(self, pokemon_id: int, chain_id: int | None) -> None:
        with self._con:
            self._con.execute(
                "UPDATE pokemon SET evolution_chain_id = ? WHERE id = ?", (chain_id, pokemon_id)
            )

    def chain_ids_to_fetch(self, *, refresh: bool = False) -> set[int]:
        """Chains referenced by stored Pokémon; only those not yet stored unless refresh."""
        query = (
            "SELECT DISTINCT evolution_chain_id FROM pokemon WHERE evolution_chain_id IS NOT NULL"
        )
        if not refresh:
            query += " AND evolution_chain_id NOT IN (SELECT id FROM evolution_chain)"
        return {row[0] for row in self._con.execute(query)}

    def upsert_chain(self, chain: EvolutionChain) -> None:
        with self._con:
            self._con.execute("DELETE FROM evolution WHERE chain_id = ?", (chain.id,))
            self._con.execute(
                "INSERT OR REPLACE INTO evolution_chain (id, root_id, root_name) VALUES (?, ?, ?)",
                (chain.id, chain.root_id, chain.root_name),
            )
            self._con.executemany(
                "INSERT INTO evolution (chain_id, position, from_id, to_id, to_name, method)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (chain.id, position, e.from_id, e.to_id, e.to_name, e.method)
                    for position, e in enumerate(chain.evolutions)
                ],
            )

    def chains(self) -> dict[int, EvolutionChain]:
        """Every stored chain by id; small enough to load whole (about 550 chains)."""
        steps: defaultdict[int, list[Evolution]] = defaultdict(list)
        for row in self._con.execute("SELECT * FROM evolution ORDER BY chain_id, position"):
            steps[row["chain_id"]].append(
                Evolution(
                    from_id=row["from_id"],
                    to_id=row["to_id"],
                    to_name=row["to_name"],
                    method=row["method"],
                )
            )
        return {
            row["id"]: EvolutionChain(
                id=row["id"],
                root_id=row["root_id"],
                root_name=row["root_name"],
                evolutions=tuple(steps[row["id"]]),
            )
            for row in self._con.execute("SELECT * FROM evolution_chain")
        }


def _to_row(pokemon: Pokemon) -> dict[str, object]:
    row = pokemon.model_dump(exclude={"stats", "fetched_at"})
    row.update(pokemon.stats.model_dump())
    return row


def _from_row(row: sqlite3.Row) -> Pokemon:
    data = dict(row)
    data["stats"] = {column: data.pop(column) for column in STAT_COLUMNS}
    return Pokemon.model_validate(data)
