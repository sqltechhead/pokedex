import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from pokedex.db import PokedexDB  # noqa: E402
from pokedex.fetcher.api import EvolutionChainResponse, EvolutionDetail  # noqa: E402
from pokedex.fetcher.evolution import build_chain, describe, display_name  # noqa: E402
from pokedex.models import BaseStats, Evolution, EvolutionChain, Pokemon  # noqa: E402
from pokedex.paths import DataPaths  # noqa: E402
from pokedex.ui.app import handle_tap  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.render import Renderer  # noqa: E402
from pokedex.ui.state import Action, PokedexState, View  # noqa: E402

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


@pytest.fixture
def state(oddish_chain: EvolutionChain) -> PokedexState:
    # Bellossom (#182) is in the chain but not the database, like a Gen 1-only fetch.
    return PokedexState([make_mon(43), make_mon(44), make_mon(45)], {18: oddish_chain})


def test_open_evolution_puts_cursor_on_current(state: PokedexState):
    state.open_species(44)
    state.handle(Action.A)
    assert state.view is View.EVOLUTION
    assert (state.evo_stage, state.evo_row) == (1, 0)
    assert state.evo_cursor == 44


def test_evolution_cursor_moves_and_clamps(state: PokedexState):
    state.open_species(43)
    state.handle(Action.A)
    state.handle(Action.LEFT)
    assert state.evo_cursor == 43
    for _ in range(3):
        state.handle(Action.RIGHT)
    assert state.evo_cursor == 45
    state.handle(Action.DOWN)
    assert state.evo_cursor == 182
    state.handle(Action.LEFT)  # row clamps to the single Gloom
    assert state.evo_cursor == 44


def test_a_opens_member_and_b_returns(state: PokedexState):
    state.open_species(43)
    state.handle(Action.A)
    state.handle(Action.RIGHT)
    state.handle(Action.A)
    assert state.view is View.DETAIL
    assert state.selected.id == 44
    state.handle(Action.A)
    state.handle(Action.B)
    assert state.view is View.DETAIL


def test_member_not_in_database_cannot_be_opened(state: PokedexState):
    state.open_species(45)
    state.handle(Action.A)
    state.handle(Action.DOWN)
    assert state.evo_cursor == 182
    state.handle(Action.A)
    assert state.view is View.EVOLUTION


def test_opening_member_clears_filter_that_hides_it(oddish_chain: EvolutionChain):
    gloom = make_mon(44).model_copy(update={"type1": "poison"})
    state = PokedexState([make_mon(43), gloom], {18: oddish_chain})
    state.set_filter("grass")
    assert state.open_species(44)
    assert state.type_filter is None
    assert state.selected.id == 44
    assert not state.open_species(999)


def test_missing_chain_data(oddish_chain: EvolutionChain):
    state = PokedexState([make_mon(43, chain_id=None)], {18: oddish_chain}, view=View.LIST)
    state.handle(Action.A)
    state.handle(Action.A)
    assert state.view is View.EVOLUTION
    assert state.evo_cursor is None
    for action in (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT, Action.A):
        state.handle(action)
    assert state.view is View.EVOLUTION
    state.handle(Action.B)
    assert state.view is View.DETAIL


EEVEE = EvolutionChain(
    id=67,
    root_id=133,
    root_name="Eevee",
    evolutions=tuple(
        Evolution(from_id=133, to_id=to, to_name=f"Eeveelution{to}", method="Some Stone")
        for to in (134, 135, 136, 196, 197, 470, 471, 700)
    ),
)


@pytest.mark.parametrize("size", [(480, 320), (800, 480), (320, 240)])
@pytest.mark.parametrize("chain_id", [18, 67, None])
def test_renders_evolution_screen(tmp_path, oddish_chain, size, chain_id):
    pygame.init()
    try:
        screen = pygame.display.set_mode(size)
        mons = [make_mon(43, chain_id), make_mon(133, chain_id)]
        state = PokedexState(mons, {18: oddish_chain, 67: EEVEE})
        state.open_species(133 if chain_id == 67 else 43)
        state.handle(Action.A)
        renderer = Renderer(screen, ImageCache(DataPaths(tmp_path)))
        renderer.draw(state)
        expected_cells = {18: 4, 67: 9, None: 0}[chain_id]
        assert len(renderer.evo_hits) == expected_cells
        for rect, _ in renderer.evo_hits:
            assert screen.get_rect().contains(rect)
    finally:
        pygame.quit()


def test_tap_evolution_cells(tmp_path, state: PokedexState):
    pygame.init()
    try:
        screen = pygame.display.set_mode((480, 320))
        renderer = Renderer(screen, ImageCache(DataPaths(tmp_path)))
        state.open_species(43)
        state.handle(Action.A)
        renderer.draw(state)
        gloom = next(rect for rect, pos in renderer.evo_hits if pos == (1, 0))
        handle_tap(gloom.center, state, renderer)
        assert state.evo_cursor == 44
        handle_tap(gloom.center, state, renderer)
        assert state.view is View.DETAIL
        assert state.selected.id == 44
    finally:
        pygame.quit()
