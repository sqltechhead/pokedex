import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from pokedex.models import BaseStats, Pokemon  # noqa: E402
from pokedex.paths import DataPaths  # noqa: E402
from pokedex.search import normalize, search  # noqa: E402
from pokedex.ui import keyboard  # noqa: E402
from pokedex.ui.app import audio_due, handle_event, handle_tap  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.render import Renderer  # noqa: E402
from pokedex.ui.state import MENU, Action, PokedexState, View  # noqa: E402

STATS = BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)
NAMES = {
    4: "Charmander",
    5: "Charmeleon",
    6: "Charizard",
    25: "Pikachu",
    122: "Mr. Mime",
    250: "Ho-Oh",
    390: "Chimchar",
    669: "Flabébé",
}


@pytest.fixture
def pokemon() -> list[Pokemon]:
    return [
        Pokemon(id=i, name=n, type1="normal", height_dm=1, weight_hg=1, stats=STATS)
        for i, n in NAMES.items()
    ]


def ids(results: list[Pokemon]) -> list[int]:
    return [p.id for p in results]


class TestMatching:
    def test_prefix_before_contains(self, pokemon):
        assert ids(search(pokemon, "char")) == [4, 5, 6, 390]

    def test_punctuation_and_accents_ignored(self, pokemon):
        assert ids(search(pokemon, "mrmime")) == [122]
        assert ids(search(pokemon, "Mr. Mime")) == [122]
        assert ids(search(pokemon, "flabebe")) == [669]
        assert ids(search(pokemon, "hooh")) == [250]

    def test_numbers(self, pokemon):
        assert ids(search(pokemon, "25")) == [25, 250]  # exact number first
        assert ids(search(pokemon, "006")) == [6]

    def test_empty_and_no_match(self, pokemon):
        assert search(pokemon, "") == []
        assert search(pokemon, "zzz") == []
        assert normalize("  ") == ""


class TestKeyboard:
    def test_wraps_horizontally(self):
        assert keyboard.move(0, 0, 0, -1) == (0, 9)

    def test_vertical_moves_keep_the_column(self):
        # From "S" (row 1, column 8) down onto OK, which spans columns 8-9.
        assert keyboard.move(1, 8, 1, 0) == keyboard.DONE_POSITION
        # From OK down to "8", and from DEL (columns 6-7) up to "Q".
        assert keyboard.move(*keyboard.DONE_POSITION, 1, 0) == (3, 8)
        assert keyboard.move(2, 6, -1, 0) == (1, 6)

    def test_wraps_vertically(self):
        assert keyboard.move(0, 0, -1, 0) == (3, 0)


@pytest.fixture
def state(pokemon) -> PokedexState:
    state = PokedexState(pokemon)
    state.open_menu(next(i for i, (_, view) in enumerate(MENU) if view is View.SEARCH))
    return state


def press(state: PokedexState, label: str) -> None:
    row, index = next(
        (r, i)
        for r, keys in enumerate(keyboard.LAYOUT)
        for i, k in enumerate(keys)
        if k.label == label
    )
    state.search.press(row, index)


class TestSearchScreen:
    def test_type_with_keys_then_open_a_result(self, state):
        for letter in "PIK":
            press(state, letter)
        assert state.search.query == "pik"
        assert ids(state.search.results) == [25]
        press(state, "OK")
        assert state.search.in_results
        state.handle(Action.A)
        assert state.view is View.DETAIL
        assert state.selected.id == 25

    def test_b_from_entry_returns_to_the_search(self, state):
        state.type_text("char")
        state.handle(Action.SELECT)
        state.handle(Action.DOWN)
        state.handle(Action.A)
        assert state.selected.id == 5
        state.handle(Action.B)
        assert state.view is View.SEARCH
        assert state.search.query == "char"
        assert state.search.result_index == 1

    def test_b_deletes_then_leaves(self, state):
        state.type_text("ab")
        state.handle(Action.B)
        assert state.search.query == "a"
        state.handle(Action.B)
        state.handle(Action.B)
        assert state.view is View.HOME

    def test_dpad_moves_the_key_cursor_and_a_types(self, state):
        state.handle(Action.RIGHT)  # A -> B
        state.handle(Action.DOWN)  # B -> L
        state.handle(Action.A)
        assert state.search.query == "l"

    def test_ok_with_no_results_stays_on_keyboard(self, state):
        state.type_text("zzz")
        press(state, "OK")
        assert not state.search.in_results

    def test_results_list_wraps_and_b_returns_to_keyboard(self, state):
        state.type_text("char")
        state.handle(Action.SELECT)
        state.handle(Action.UP)
        assert state.search.selected.id == 390
        state.handle(Action.B)
        assert not state.search.in_results
        assert state.view is View.SEARCH

    def test_query_length_is_capped(self, state):
        state.type_text("a" * 30)
        assert len(state.search.query) == 12

    def test_typing_moves_cursor_to_ok_and_ignores_symbols(self, state):
        state.type_text("Mr. Mime!")
        assert state.search.query == "mrmime"
        assert (state.search.key_row, state.search.key_index) == keyboard.DONE_POSITION
        state.handle(Action.A)  # Enter presses OK
        assert state.search.in_results

    def test_typing_elsewhere_does_nothing(self, pokemon):
        home = PokedexState(pokemon)
        home.type_text("pika")
        assert home.search.query == ""


class TestApp:
    @pytest.fixture
    def renderer(self, tmp_path):
        pygame.init()
        yield Renderer(pygame.display.set_mode((480, 320)), ImageCache(DataPaths(tmp_path)))
        pygame.quit()

    def test_letter_keys_type_instead_of_pressing_buttons(self, state, renderer):
        for key, text in ((pygame.K_z, "z"), (pygame.K_s, "s"), (pygame.K_x, "x")):
            handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0), state, renderer)
            handle_event(pygame.event.Event(pygame.TEXTINPUT, text=text), state, renderer)
        assert state.search.query == "zsx"
        assert state.view is View.SEARCH
        handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0), state, renderer
        )
        assert state.search.query == "zs"

    def test_entry_opened_from_search_cries(self, state):
        state.type_text("pikachu")
        before = (state.view, state.selected.id)
        state.handle(Action.SELECT)
        state.handle(Action.A)
        assert audio_due(before, state)

    def test_tap_keys_and_results(self, state, renderer):
        renderer.draw(state)
        for label in "CHA":
            rect = next(
                r for r, (row, i) in renderer.key_hits if keyboard.LAYOUT[row][i].label == label
            )
            handle_tap(rect.center, state, renderer)
        assert state.search.query == "cha"
        renderer.draw(state)
        first = next(r for r, index in renderer.result_hits if index == 2)
        handle_tap(first.center, state, renderer)
        assert state.view is View.DETAIL
        assert state.selected.id == 6

    def test_tap_header_goes_home(self, state, renderer):
        state.type_text("abc")
        renderer.draw(state)
        handle_tap(renderer.header.center, state, renderer)
        assert state.view is View.HOME


@pytest.mark.parametrize("size", [(480, 320), (800, 480), (320, 240)])
@pytest.mark.parametrize("query", ["", "char", "zzz"])
def test_renders_search_screen(tmp_path, state, size, query):
    pygame.init()
    try:
        screen = pygame.display.set_mode(size)
        renderer = Renderer(screen, ImageCache(DataPaths(tmp_path)))
        state.type_text(query)
        state.search.in_results = bool(state.search.results)
        renderer.draw(state)
        keys = sum(len(row) for row in keyboard.LAYOUT)
        assert len(renderer.key_hits) == keys
        assert len(renderer.result_hits) == min(len(state.search.results), 99)
        for rect, _ in renderer.key_hits + renderer.result_hits:
            assert screen.get_rect().contains(rect)
    finally:
        pygame.quit()
