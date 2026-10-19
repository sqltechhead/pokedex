import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from pokedex.models import BaseStats, Pokemon  # noqa: E402
from pokedex.paths import DataPaths  # noqa: E402
from pokedex.ui.app import handle_tap  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.render import Renderer  # noqa: E402
from pokedex.ui.settings import Settings  # noqa: E402
from pokedex.ui.state import MENU, Action, PokedexState, View  # noqa: E402

STATS = BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)


@pytest.fixture
def state() -> PokedexState:
    mons = [
        Pokemon(id=i, name=f"Mon{i}", type1="normal", height_dm=1, weight_hg=1, stats=STATS)
        for i in (1, 2, 3)
    ]
    return PokedexState(mons)


def menu_index(view: View) -> int:
    return next(i for i, (_, target) in enumerate(MENU) if target is view)


def test_starts_on_home_and_every_entry_opens_and_returns(state: PokedexState):
    assert state.view is View.HOME
    for index, (_, view) in enumerate(MENU):
        assert state.menu_index == index
        state.handle(Action.A)
        assert state.view is view
        state.handle(Action.B)
        assert state.view is View.HOME
        state.handle(Action.DOWN)


def test_menu_wraps_and_remembers_choice(state: PokedexState):
    state.handle(Action.UP)
    assert state.menu_index == len(MENU) - 1
    state.handle(Action.A)
    state.handle(Action.B)
    assert state.menu_index == len(MENU) - 1


def test_b_in_filtered_list_clears_filter_before_going_home(state: PokedexState):
    state.open_menu(0)
    state.set_filter("normal")
    state.handle(Action.B)
    assert state.view is View.LIST
    assert state.type_filter is None
    state.handle(Action.B)
    assert state.view is View.HOME


def test_settings_change_with_dpad_and_a(state: PokedexState):
    state.open_menu(menu_index(View.SETTINGS))
    state.handle(Action.LEFT)  # volume 80% -> 70%
    assert state.settings.volume == pytest.approx(0.7)
    state.handle(Action.A)  # A does nothing on the volume row
    assert state.settings.volume == pytest.approx(0.7)
    state.handle(Action.DOWN)
    state.handle(Action.A)
    assert state.settings.sound is False
    state.handle(Action.RIGHT)
    assert state.settings.sound is True


def test_volume_stays_in_range():
    settings = Settings(volume=0.95)
    assert settings.adjusted("volume", 1).volume == 1.0
    assert Settings(volume=0.05).adjusted("volume", -1).volume == 0.0
    assert settings.describe("volume") == "95%"
    assert Settings(cry=False).describe("cry") == "Off"


def test_settings_saved_and_loaded(tmp_path):
    path = tmp_path / "settings.json"
    assert Settings.load(path) == Settings()  # no file: defaults
    Settings(volume=0.3, narration=False).save(path)
    assert Settings.load(path) == Settings(volume=0.3, narration=False)
    path.write_text("{not json")
    assert Settings.load(path) == Settings()  # damaged file: defaults


@pytest.fixture
def renderer(tmp_path):
    pygame.init()
    yield Renderer(pygame.display.set_mode((480, 320)), ImageCache(DataPaths(tmp_path)))
    pygame.quit()


def test_tap_home_entries_and_header(renderer: Renderer, state: PokedexState):
    renderer.draw(state)
    settings = menu_index(View.SETTINGS)
    settings_row = next(rect for rect, index in renderer.menu_hits if index == settings)
    handle_tap(settings_row.center, state, renderer)
    assert state.view is View.SETTINGS
    renderer.draw(state)
    handle_tap(renderer.header.center, state, renderer)
    assert state.view is View.HOME


def test_tap_settings_rows(renderer: Renderer, state: PokedexState):
    state.open_menu(menu_index(View.SETTINGS))
    renderer.draw(state)
    volume = next(rect for rect, row in renderer.settings_hits if row == 0)
    handle_tap((volume.right - 5, volume.centery), state, renderer)
    assert state.settings.volume == pytest.approx(0.9)
    handle_tap((volume.left + 5, volume.centery), state, renderer)
    assert state.settings.volume == pytest.approx(0.8)
    cries = next(rect for rect, row in renderer.settings_hits if row == 2)
    handle_tap(cries.center, state, renderer)
    assert state.settings.cry is False
