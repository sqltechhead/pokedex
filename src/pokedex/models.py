"""Pokémon records shared by the fetcher and the Pokédex UI."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    hp: int
    attack: int
    defense: int
    sp_attack: int
    sp_defense: int
    speed: int

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class PokemonAbility(BaseModel):
    model_config = ConfigDict(frozen=True)

    ability_id: int
    hidden: bool = False


class LevelMove(BaseModel):
    """A move learned by levelling up, e.g. Thunder Shock at level 1."""

    model_config = ConfigDict(frozen=True)

    level: int
    move_id: int


class Move(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    type: str
    power: int | None = None
    damage_class: str | None = None
    """physical, special or status."""


class Ability(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    description: str = ""


class Pokemon(BaseModel):
    """One National Pokédex entry, as stored in the database."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    genus: str | None = None
    type1: str
    type2: str | None = None
    height_dm: int
    """Height in decimetres, as PokéAPI stores it."""
    weight_hg: int
    """Weight in hectograms, as PokéAPI stores it."""
    stats: BaseStats
    flavor_text: str = ""
    sprite_path: str | None = None
    """96x96 game sprite, relative to the data folder."""
    artwork_path: str | None = None
    """475x475 official artwork, relative to the data folder."""
    cry_path: str | None = None
    """Modern cry audio, relative to the data folder."""
    narration_path: str | None = None
    """Spoken Pokédex entry, relative to the data folder."""
    evolution_chain_id: int | None = None
    generation: int | None = None
    """1 (Kanto) to 9 (Paldea). None on rows fetched before regions were stored."""
    shiny_artwork_path: str | None = None
    """Shiny official artwork, relative to the data folder."""
    abilities: tuple[PokemonAbility, ...] = ()
    level_moves: tuple[LevelMove, ...] = ()
    """Level-up moves in move_version, by level."""
    move_version: str | None = None
    """The game the moves are from, e.g. "scarlet-violet" (the newest with level-up data)."""
    color: str | None = None
    """PokéAPI's colour, e.g. "pink". None on rows fetched before it was stored."""
    shape: str | None = None
    """e.g. "quadruped" (four legs)."""
    habitat: str | None = None
    """e.g. "forest"; Gen 1-3 only."""
    legendary: bool = False
    mythical: bool = False
    baby: bool = False
    egg_groups: tuple[str, ...] = ()
    fetched_at: datetime | None = None

    @property
    def types(self) -> tuple[str, ...]:
        return (self.type1,) if self.type2 is None else (self.type1, self.type2)

    @property
    def height_m(self) -> float:
        return self.height_dm / 10

    @property
    def weight_kg(self) -> float:
        return self.weight_hg / 10


class Evolution(BaseModel):
    """One step of a chain, e.g. Charmander -> Charmeleon at "Lv. 16"."""

    model_config = ConfigDict(frozen=True)

    from_id: int
    to_id: int
    to_name: str
    """Display name from the chain, for species not in the database."""
    method: str


class EvolutionChain(BaseModel):
    """A family tree of species; most are a line, some branch (Eevee, Oddish)."""

    model_config = ConfigDict(frozen=True)

    id: int
    root_id: int
    root_name: str
    evolutions: tuple[Evolution, ...] = ()

    def stages(self) -> list[list[int]]:
        """Species IDs grouped by evolution stage: [[root], [stage 1, ...], ...]."""
        stages = [[self.root_id]]
        while True:
            # Children follow their parent's order, so branches stay in rows.
            next_stage = [
                e.to_id for parent in stages[-1] for e in self.evolutions if e.from_id == parent
            ]
            if not next_stage:
                return stages
            stages.append(next_stage)

    def name(self, species_id: int) -> str:
        if species_id == self.root_id:
            return self.root_name
        return next(e.to_name for e in self.evolutions if e.to_id == species_id)

    def evolution_to(self, species_id: int) -> Evolution | None:
        return next((e for e in self.evolutions if e.to_id == species_id), None)
