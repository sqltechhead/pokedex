"""Search ranking, the on-screen keyboard, and the search screen's buttons."""

import pytest
from conftest import ids

from dex import keyboard
from dex import state as s
from dex.index import Dex
from dex.search import normalize, search
from dex.state import MAX_QUERY, MENU, PokedexState


class TestSearch:
    def test_prefix_before_contains(self, dex: Dex):
        assert ids(dex, search(dex, "char")) == [4, 5, 6]
        assert ids(dex, search(dex, "e")) == [133, 4, 5, 7, 122, 669]

    def test_punctuation_and_case_ignored(self, dex: Dex):
        assert ids(dex, search(dex, "Mr. Mime")) == [122]
        assert ids(dex, search(dex, "flabebe")) == [669]
        assert normalize("Nidoran♀") == "nidoran"

    def test_numbers(self, dex: Dex):
        assert ids(dex, search(dex, "25")) == [25]
        assert ids(dex, search(dex, "00")) == [1, 4, 5, 6, 7]
        assert ids(dex, search(dex, "02")) == [25, 29]
        assert ids(dex, search(dex, "6")) == [6, 669]

    def test_empty_and_no_match(self, dex: Dex):
        assert search(dex, "") == []
        assert search(dex, "!!") == []
        assert search(dex, "zzz") == []


class TestKeyboard:
    def test_wraps_horizontally(self):
        assert keyboard.move(0, 9, 0, 1) == (0, 0)

    def test_vertical_moves_keep_the_column(self):
        assert keyboard.move(1, 8, 1, 0) == keyboard.DONE_POSITION  # S -> OK
        assert keyboard.move(2, 6, 1, 0) == (3, 6)  # DEL -> 6
        assert keyboard.move(3, 7, -1, 0) == (2, 6)  # 7 -> DEL

    def test_wraps_vertically(self):
        assert keyboard.move(0, 0, -1, 0) == (3, 0)


@pytest.fixture
def search_state(state: PokedexState) -> PokedexState:
    state.open_menu(next(i for i, (_, view) in enumerate(MENU) if view == s.SEARCH))
    return state


def press(state: PokedexState, label: str) -> None:
    """Move the cursor to a key with the D-pad, then press A."""
    target = next(
        (r, i)
        for r, row in enumerate(keyboard.LAYOUT)
        for i, key in enumerate(row)
        if key[keyboard.LABEL] == label
    )
    st = state.search
    st.key_row, st.key_index = target
    state.handle(s.A)


class TestSearchScreen:
    def test_type_with_keys_then_open_a_result(self, search_state: PokedexState):
        for label in "CHAR":
            press(search_state, label)
        assert search_state.search.query == "char"
        assert ids(search_state.dex, search_state.search.results) == [4, 5, 6]
        press(search_state, "OK")
        assert search_state.search.in_results
        search_state.handle(s.DOWN)
        search_state.handle(s.A)
        assert search_state.view == s.DETAIL
        assert search_state.selected_id == 5

    def test_b_from_an_entry_returns_to_the_search(self, search_state: PokedexState):
        press(search_state, "P")
        press(search_state, "OK")
        search_state.handle(s.A)
        search_state.handle(s.B)
        assert search_state.view == s.SEARCH
        assert search_state.search.query == "p"

    def test_b_deletes_then_leaves(self, search_state: PokedexState):
        press(search_state, "E")
        search_state.handle(s.B)
        assert search_state.search.query == ""
        assert search_state.view == s.SEARCH
        search_state.handle(s.B)
        assert search_state.view == s.HOME

    def test_dpad_moves_the_key_cursor(self, search_state: PokedexState):
        search_state.handle(s.RIGHT)
        search_state.handle(s.DOWN)
        search_state.handle(s.A)
        assert search_state.search.query == "l"

    def test_ok_with_no_results_stays_on_the_keyboard(self, search_state: PokedexState):
        press(search_state, "X")
        press(search_state, "OK")
        assert not search_state.search.in_results

    def test_results_wrap_and_b_returns_to_the_keyboard(self, search_state: PokedexState):
        for label in "CHAR":
            press(search_state, label)
        search_state.handle(s.SELECT)
        search_state.handle(s.UP)
        assert search_state.search.result_index == 2
        search_state.handle(s.B)
        assert not search_state.search.in_results
        assert search_state.view == s.SEARCH

    def test_query_length_is_capped(self, search_state: PokedexState):
        for _ in range(MAX_QUERY + 3):
            press(search_state, "A")
        assert len(search_state.search.query) == MAX_QUERY

    def test_delete_key(self, search_state: PokedexState):
        press(search_state, "A")
        press(search_state, "DEL")
        press(search_state, "DEL")
        assert search_state.search.query == ""
        assert search_state.view == s.SEARCH
