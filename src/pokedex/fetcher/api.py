"""Typed client for the parts of PokéAPI the Pokédex uses.

The response models declare only the fields we read; Pydantic ignores the rest.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

import requests
from pydantic import BaseModel, Field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = "https://pokeapi.co/api/v2"
USER_AGENT = "pi-pokedex/0.1 (personal project)"


def id_from_url(url: str) -> int:
    """PokéAPI resource URLs end in their id: ``.../pokemon-species/25/`` -> 25."""
    return int(url.rstrip("/").rsplit("/", 1)[-1])


class APIResource(BaseModel):
    url: str

    @property
    def id(self) -> int:
        return id_from_url(self.url)


class NamedResource(BaseModel):
    name: str
    url: str = ""

    @property
    def id(self) -> int:
        return id_from_url(self.url)


class TypeSlot(BaseModel):
    slot: int
    type: NamedResource


class StatEntry(BaseModel):
    base_stat: int
    stat: NamedResource


class Artwork(BaseModel):
    front_default: str | None = None
    front_shiny: str | None = None


class OtherSprites(BaseModel):
    official_artwork: Artwork = Field(default_factory=Artwork, alias="official-artwork")


class Sprites(BaseModel):
    front_default: str | None = None
    other: OtherSprites | None = None

    @property
    def artwork_url(self) -> str | None:
        return self.other.official_artwork.front_default if self.other else None

    @property
    def shiny_artwork_url(self) -> str | None:
        return self.other.official_artwork.front_shiny if self.other else None


class Cries(BaseModel):
    latest: str | None = None
    """Modern cry. Named .ogg, though some are MP3 inside; pygame plays both."""
    legacy: str | None = None
    """Original Game Boy-era cry; older Pokémon only."""


class AbilitySlot(BaseModel):
    ability: NamedResource
    is_hidden: bool = False
    slot: int = 0


class VersionGroupDetail(BaseModel):
    level_learned_at: int
    move_learn_method: NamedResource
    version_group: NamedResource


class MoveSlot(BaseModel):
    move: NamedResource
    version_group_details: list[VersionGroupDetail] = []


class PokemonResponse(BaseModel):
    """``/pokemon/{id}``: types, stats, size, abilities, moves, image and cry URLs."""

    id: int
    name: str
    height: int
    weight: int
    types: list[TypeSlot]
    stats: list[StatEntry]
    sprites: Sprites
    cries: Cries = Field(default_factory=Cries)
    abilities: list[AbilitySlot] = []
    moves: list[MoveSlot] = []

    @property
    def type_names(self) -> list[str]:
        return [t.type.name for t in sorted(self.types, key=lambda t: t.slot)]


class LocalizedName(BaseModel):
    name: str
    language: NamedResource


class LocalizedGenus(BaseModel):
    genus: str
    language: NamedResource


class FlavorTextEntry(BaseModel):
    flavor_text: str
    language: NamedResource
    version: NamedResource


class SpeciesResponse(BaseModel):
    """``/pokemon-species/{id}``: display name, genus and Pokédex text."""

    id: int
    name: str
    names: list[LocalizedName]
    genera: list[LocalizedGenus]
    flavor_text_entries: list[FlavorTextEntry]
    evolution_chain: APIResource | None = None
    generation: NamedResource | None = None
    color: NamedResource | None = None
    shape: NamedResource | None = None
    habitat: NamedResource | None = None
    is_legendary: bool = False
    is_mythical: bool = False
    is_baby: bool = False
    egg_groups: list[NamedResource] = []

    @property
    def english_name(self) -> str:
        return next((n.name for n in self.names if n.language.name == "en"), self.name.title())

    @property
    def english_genus(self) -> str | None:
        return next((g.genus for g in self.genera if g.language.name == "en"), None)

    def flavor_text(self, versions: Sequence[str]) -> str:
        """English entry from the first game in versions, else the newest English entry."""
        english = [e for e in self.flavor_text_entries if e.language.name == "en"]
        if not english:
            return ""
        by_version = {e.version.name: e.flavor_text for e in english}
        text = next((by_version[v] for v in versions if v in by_version), english[-1].flavor_text)
        return clean_text(text)


class EvolutionDetail(BaseModel):
    """One way of evolving; PokéAPI lists one per game where the method differs."""

    is_default: bool = False
    trigger: NamedResource | None = None
    min_level: int | None = None
    item: NamedResource | None = None
    held_item: NamedResource | None = None
    known_move: NamedResource | None = None
    used_move: NamedResource | None = None
    min_move_count: int | None = None
    known_move_type: NamedResource | None = None
    location: NamedResource | None = None
    party_species: NamedResource | None = None
    party_type: NamedResource | None = None
    trade_species: NamedResource | None = None
    min_happiness: int | None = None
    min_affection: int | None = None
    min_beauty: int | None = None
    gender: int | None = None
    """1 female, 2 male."""
    time_of_day: str = ""
    relative_physical_stats: int | None = None
    """1 Attack > Defense, -1 Attack < Defense, 0 equal."""
    needs_overworld_rain: bool = False
    turn_upside_down: bool = False


class ChainLink(BaseModel):
    species: NamedResource
    evolution_details: list[EvolutionDetail] = []
    evolves_to: list["ChainLink"] = []


class EvolutionChainResponse(BaseModel):
    """``/evolution-chain/{id}``: the species tree and how each step happens."""

    id: int
    chain: ChainLink


class AbilityFlavorText(BaseModel):
    flavor_text: str
    language: NamedResource
    version_group: NamedResource


class AbilityResponse(BaseModel):
    """``/ability/{id}``: display name and a short description."""

    id: int
    name: str
    names: list[LocalizedName] = []
    flavor_text_entries: list[AbilityFlavorText] = []

    @property
    def english_name(self) -> str:
        return english_name(self.names, self.name)

    @property
    def description(self) -> str:
        """The newest English in-game description."""
        english = [e for e in self.flavor_text_entries if e.language.name == "en"]
        if not english:
            return ""
        return clean_text(max(english, key=lambda e: e.version_group.id).flavor_text)


class MoveResponse(BaseModel):
    """``/move/{id}``: display name, type and power."""

    id: int
    name: str
    names: list[LocalizedName] = []
    type: NamedResource
    power: int | None = None
    damage_class: NamedResource | None = None

    @property
    def english_name(self) -> str:
        return english_name(self.names, self.name)


class DamageRelations(BaseModel):
    double_damage_to: list[NamedResource] = []
    half_damage_to: list[NamedResource] = []
    no_damage_to: list[NamedResource] = []


class TypeResponse(BaseModel):
    """``/type/{name}``: how much damage this type's attacks do to each type."""

    name: str
    damage_relations: DamageRelations


def english_name(names: list[LocalizedName], fallback: str) -> str:
    """The English name, else the slug made readable ("thunder-shock" -> "Thunder Shock")."""
    return next(
        (n.name for n in names if n.language.name == "en"), fallback.replace("-", " ").title()
    )


def clean_text(text: str) -> str:
    """Strip the original games' line/page breaks and soft hyphens from flavour text."""
    text = text.replace("\f", " ").replace("\n", " ").replace("­", "")
    return re.sub(r"\s+", " ", text).strip()


class PokeAPIClient:
    """HTTP session with retries (including on 429 rate limits) and typed responses."""

    def __init__(self, base_url: str = API_URL, timeout: float = 20.0) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(total=5, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = USER_AGENT

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
        self.session.close()

    def _get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

    def pokemon(self, pokemon_id: int) -> PokemonResponse:
        return PokemonResponse.model_validate_json(
            self._get(f"{self.base_url}/pokemon/{pokemon_id}").content
        )

    def species(self, pokemon_id: int) -> SpeciesResponse:
        return SpeciesResponse.model_validate_json(
            self._get(f"{self.base_url}/pokemon-species/{pokemon_id}").content
        )

    def evolution_chain(self, chain_id: int) -> EvolutionChainResponse:
        return EvolutionChainResponse.model_validate_json(
            self._get(f"{self.base_url}/evolution-chain/{chain_id}").content
        )

    def ability(self, ability_id: int) -> AbilityResponse:
        return AbilityResponse.model_validate_json(
            self._get(f"{self.base_url}/ability/{ability_id}").content
        )

    def move(self, move_id: int) -> MoveResponse:
        return MoveResponse.model_validate_json(
            self._get(f"{self.base_url}/move/{move_id}").content
        )

    def type(self, name: str) -> TypeResponse:
        return TypeResponse.model_validate_json(self._get(f"{self.base_url}/type/{name}").content)

    def download(self, url: str, dest: Path) -> None:
        dest.write_bytes(self._get(url).content)
