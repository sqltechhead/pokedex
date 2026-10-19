import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from pokedex.models import BaseStats, Pokemon  # noqa: E402
from pokedex.paths import DataPaths  # noqa: E402
from pokedex.ui.app import handle_tap  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.render import Renderer, ellipsize, wrap  # noqa: E402
from pokedex.ui.state import Action, PokedexState, View  # noqa: E402

STATS = BaseStats(hp=45, attack=49, defense=49, sp_attack=65, sp_defense=65, speed=45)


def mon(pid: int, type1: str, type2: str | None = None) -> Pokemon:
    return Pokemon(
        id=pid,
        name=f"Mon{pid}",
        type1=type1,
        type2=type2,
        height_dm=7,
        weight_hg=69,
        stats=STATS,
        flavor_text="A strange seed was planted on its back at birth. " * 4,
    )


@pytest.fixture
def state() -> PokedexState:
    return PokedexState(
        [mon(1, "grass", "poison"), mon(4, "fire"), mon(6, "fire", "flying"), mon(7, "water")],
        page_size=2,
        view=View.LIST,
    )


def test_up_down_wrap(state: PokedexState):
    state.handle(Action.UP)
    assert state.selected.id == 7
    state.handle(Action.DOWN)
    assert state.selected.id == 1


def test_page_jumps_stop_at_ends(state: PokedexState):
    state.handle(Action.RIGHT)
    state.handle(Action.RIGHT)
    assert state.selected.id == 7
    state.handle(Action.LEFT)
    state.handle(Action.LEFT)
    state.handle(Action.LEFT)
    assert state.selected.id == 1


def test_open_browse_and_close_detail(state: PokedexState):
    state.handle(Action.A)
    assert state.view is View.DETAIL
    state.handle(Action.RIGHT)
    assert state.selected.id == 4
    state.handle(Action.B)
    assert state.view is View.LIST
    assert state.selected.id == 4


def test_filter_cycles_in_type_order(state: PokedexState):
    assert state.available_types == ["fire", "water", "grass", "poison", "flying"]
    state.handle(Action.SELECT)
    assert state.type_filter == "fire"
    assert [p.id for p in state.visible] == [4, 6]
    for _ in state.available_types:
        state.handle(Action.SELECT)
    assert state.type_filter is None
    assert len(state.visible) == 4


def test_filter_keeps_selection_when_possible(state: PokedexState):
    state.select_index(2)  # #6, fire/flying
    state.set_filter("flying")
    assert state.selected.id == 6
    state.set_filter("water")
    assert state.selected.id == 7


def test_b_clears_filter(state: PokedexState):
    state.set_filter("fire")
    state.handle(Action.B)
    assert state.type_filter is None


def test_empty_list_ignores_input():
    state = PokedexState([], view=View.LIST)
    for action in (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT, Action.A, Action.SELECT):
        state.handle(action)
    assert state.selected is None
    assert state.view is View.LIST


@pytest.fixture
def screen():
    pygame.init()
    yield pygame.display.set_mode((480, 320))
    pygame.quit()


@pytest.mark.parametrize("size", [(480, 320), (800, 480), (320, 240)])
def test_renders_every_screen(tmp_path, state: PokedexState, size):
    pygame.init()
    try:
        surface = pygame.display.set_mode(size)
        renderer = Renderer(surface, ImageCache(DataPaths(tmp_path)))  # no images: placeholders
        renderer.draw(state)
        assert renderer.row_hits
        state.handle(Action.A)
        renderer.draw(state)
        renderer.draw(PokedexState([], view=View.LIST))
        for view in (View.HOME, View.SCANNER, View.SETTINGS):
            renderer.draw(PokedexState(state.pokemon, view=view))
            assert renderer.menu_hits or renderer.settings_hits or view is View.SCANNER
    finally:
        pygame.quit()


def test_tap_selects_then_opens(tmp_path, screen, state: PokedexState):
    renderer = Renderer(screen, ImageCache(DataPaths(tmp_path)))
    renderer.draw(state)
    second_row, index = renderer.row_hits[1]
    handle_tap(second_row.center, state, renderer)
    assert state.index == index
    assert state.view is View.LIST
    handle_tap(second_row.center, state, renderer)
    assert state.view is View.DETAIL

    renderer.draw(state)
    handle_tap((renderer.w - 5, renderer.h // 2), state, renderer)
    assert state.index == index + 1
    handle_tap(screen.get_rect().center, state, renderer)
    assert state.view is View.EVOLUTION
    handle_tap(renderer.header.center, state, renderer)
    assert state.view is View.DETAIL
    handle_tap(renderer.header.center, state, renderer)
    assert state.view is View.LIST


def test_wrap_and_ellipsize(screen):
    font = pygame.font.Font(None, 20)
    lines = wrap("one two three four five six seven", font, 60)
    assert len(lines) > 1
    assert all(font.size(line)[0] <= 60 for line in lines if " " in line)
    assert font.size(ellipsize("a very long genus name indeed", font, 50))[0] <= 50
