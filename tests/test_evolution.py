import pytest

from pokedex.db import PokedexDB
from pokedex.fetcher.api import EvolutionChainResponse, EvolutionDetail
from pokedex.fetcher.evolution import build_chain, describe, display_name
from pokedex.models import BaseStats, EvolutionChain, Pokemon

STATS = BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)


def species(name: str, pid: int) -> dict:
    return {"name": name, "url": f"https://pokeapi.co/api/v2/pokemon-species/{pid}/"}


def detail(**fields) -> dict:
    return {"trigger": {"name": "level-up", "url": ""}, "is_default": True, **fields}


# Trimmed /evolution-chain/18: Oddish -> Gloom -> Vileplume / Bellossom.
ODDISH_CHAIN = {
    "id": 18,
    "baby_trigger_item": None,
    "chain": {
        "species": species("oddish", 43),
        "evolution_details": [],
        "evolves_to": [
            {
                "species": species("gloom", 44),
                "evolution_details": [detail(min_level=21)],
                "evolves_to": [
                    {
                        "species": species("vileplume", 45),
                        "evolution_details": [
                            detail(trigger={"name": "use-item"}, item={"name": "leaf-stone"})
                        ],
                        "evolves_to": [],
                    },
                    {
                        "species": species("bellossom", 182),
                        "evolution_details": [
                            detail(trigger={"name": "use-item"}, item={"name": "sun-stone"})
                        ],
                        "evolves_to": [],
                    },
                ],
            }
        ],
    },
}


@pytest.fixture
def oddish_chain() -> EvolutionChain:
    return build_chain(EvolutionChainResponse.model_validate(ODDISH_CHAIN))


def test_build_chain(oddish_chain: EvolutionChain):
    assert oddish_chain.root_id == 43
    assert oddish_chain.stages() == [[43], [44], [45, 182]]
    assert oddish_chain.name(182) == "Bellossom"
    assert oddish_chain.evolution_to(44).method == "Lv. 21"
    assert oddish_chain.evolution_to(45).method == "Leaf Stone"
    assert oddish_chain.evolution_to(43) is None


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        ([detail(min_happiness=160, time_of_day="day")], "High friendship, day"),
        (
            [detail(trigger={"name": "trade"}, held_item={"name": "kings-rock"})],
            "Trade holding King’s Rock",
        ),
        ([detail(min_level=20, relative_physical_stats=1)], "Lv. 20, Atk > Def"),
        (
            [
                detail(
                    trigger={"name": "use-move"}, used_move={"name": "rage-fist"}, min_move_count=20
                )
            ],
            "Use Rage Fist 20×",
        ),
        ([detail(min_level=20, gender=1)], "Lv. 20, female"),
        # Several per-game methods: the default one wins (Leafeon).
        (
            [
                detail(is_default=False, location={"name": "eterna-forest"}),
                detail(trigger={"name": "use-item"}, item={"name": "leaf-stone"}),
            ],
            "Leaf Stone",
        ),
        ([], ""),
    ],
)
def test_describe(details, expected):
    assert describe([EvolutionDetail.model_validate(d) for d in details]) == expected


def test_display_name():
    assert display_name("mr-mime") == "Mr. Mime"
    assert display_name("nidoran-f") == "Nidoran♀"
    assert display_name("bellossom") == "Bellossom"


def test_chain_round_trip(tmp_path, oddish_chain: EvolutionChain):
    with PokedexDB(tmp_path / "pokedex.db") as db:
        db.upsert(make_mon(43, chain_id=18))
        db.upsert(make_mon(44, chain_id=None))
        assert db.ids_without_chain() == {44}
        assert db.chain_ids_to_fetch() == {18}

        db.upsert_chain(oddish_chain)
        db.upsert_chain(oddish_chain)  # replacing must not duplicate steps
        assert db.chains() == {18: oddish_chain}
        assert db.chain_ids_to_fetch() == set()
        assert db.chain_ids_to_fetch(refresh=True) == {18}

        db.set_evolution_chain_id(44, 18)
        assert db.ids_without_chain() == set()


def test_single_stage_chain_is_stored(tmp_path):
    tauros = EvolutionChain(id=63, root_id=128, root_name="Tauros")
    with PokedexDB(tmp_path / "pokedex.db") as db:
        db.upsert_chain(tauros)
        assert db.chains()[63].stages() == [[128]]


def make_mon(pid: int, chain_id: int | None = 18) -> Pokemon:
    return Pokemon(
        id=pid,
        name=f"Mon{pid}",
        type1="grass",
        height_dm=1,
        weight_hg=1,
        stats=STATS,
        evolution_chain_id=chain_id,
    )
