"""Home, list, entry and evolution screens: what each button does."""

import pytest
from conftest import ENTRIES, entry, ids

from dex import state as s
from dex.index import Dex
from dex.state import MENU, PokedexState, audio_due


def menu_index(view: int) -> int:
    return next(i for i, (_, v) in enumerate(MENU) if v == view)


def test_starts_on_home_and_every_entry_opens_and_returns(state: PokedexState):
    assert state.view == s.HOME
    for index, (_, view) in enumerate(MENU):
        state.menu_index = index
        state.handle(s.A)
        assert state.view == view
        state.handle(s.B)
        assert state.view == s.HOME


def test_menu_wraps_and_remembers_choice(state: PokedexState):
    state.handle(s.UP)
    assert state.menu_index == len(MENU) - 1
    state.handle(s.A)
    state.handle(s.B)
    assert state.menu_index == len(MENU) - 1


def open_list(state: PokedexState) -> None:
    state.open_menu(menu_index(s.LIST))


def test_up_down_wrap(state: PokedexState):
    open_list(state)
    state.handle(s.UP)
    assert state.selected_id == 669
    state.handle(s.DOWN)
    assert state.selected_id == 1


def test_page_jumps_stop_at_ends(state: PokedexState):
    open_list(state)
    state.page_size = 4
    state.handle(s.RIGHT)
    assert state.index == 4
    state.handle(s.RIGHT)
    state.handle(s.RIGHT)
    assert state.index == len(ENTRIES) - 1
    state.handle(s.LEFT)
    state.handle(s.LEFT)
    state.handle(s.LEFT)
    assert state.index == 0


def test_open_browse_and_close_entry(state: PokedexState):
    open_list(state)
    state.handle(s.A)
    assert state.view == s.DETAIL
    state.handle(s.RIGHT)
    assert state.selected_id == 4
    assert state.entry["genus"] == "Test Pokémon"
    state.handle(s.B)
    assert state.view == s.LIST
    assert state.selected_id == 4


def test_filter_cycles_in_type_order(state: PokedexState):
    open_list(state)
    seen = []
    for _ in range(len(state.available_types) + 1):
        state.handle(s.R)
        seen.append(state.type_filter)
    assert seen[:3] == ["normal", "fire", "water"]
    assert seen[-1] is None
    state.handle(s.L)
    assert state.type_filter == state.available_types[-1]  # L goes backwards, wrapping


def test_filter_keeps_selection_when_possible(state: PokedexState):
    open_list(state)
    state.open_species(6)
    state.view = s.LIST
    state.set_filter("flying")
    assert state.selected_id == 6
    state.set_filter("water")
    assert state.selected_id == 7


def test_b_clears_filter_before_going_home(state: PokedexState):
    open_list(state)
    state.set_filter("fire")
    assert ids(state.dex, state.visible) == [4, 5, 6]
    state.handle(s.B)
    assert state.type_filter is None
    assert state.view == s.LIST
    state.handle(s.B)
    assert state.view == s.HOME


def test_empty_dex_ignores_input():
    state = PokedexState(Dex(), entry)
    open_list(state)
    for action in (s.UP, s.DOWN, s.LEFT, s.RIGHT, s.A, s.SELECT, s.L, s.R):
        state.handle(action)
    assert state.view == s.LIST
    assert state.selected is None
    assert state.entry is None


def test_select_replays_the_entry(state: PokedexState):
    open_list(state)
    state.handle(s.A)
    state.handle(s.SELECT)
    assert state.replay
    assert state.view == s.DETAIL


@pytest.mark.parametrize("view", [s.LIST, s.DETAIL, s.EVOLUTION, s.SEARCH, s.SETTINGS])
def test_start_opens_the_menu_from_anywhere(state: PokedexState, view: int):
    open_list(state)
    state.handle(s.A)
    state.view = view
    state.handle(s.START)
    assert state.view == s.HOME


def test_shoulders_jump_ten_entries_on_an_entry(state: PokedexState):
    open_list(state)
    state.handle(s.A)
    state.handle(s.R)
    assert state.index == min(10, len(state.visible) - 1)  # stops at the end
    state.handle(s.L)
    state.handle(s.L)
    assert state.index == 0


def test_audio_plays_on_open_and_change_not_on_return(state: PokedexState):
    open_list(state)
    before = (state.view, state.selected_id)
    state.handle(s.A)
    assert audio_due(before, state)

    before = (state.view, state.selected_id)
    state.handle(s.RIGHT)
    assert audio_due(before, state)

    state.handle(s.A)  # to the evolution screen and back to the same entry
    before = (state.view, state.selected_id)
    state.handle(s.B)
    assert not audio_due(before, state)


# Evolution


def open_evolution(state: PokedexState, pokemon_id: int) -> None:
    state.open_species(pokemon_id)
    state.handle(s.A)


def test_evolution_cursor_starts_on_the_current_pokemon(state: PokedexState):
    open_evolution(state, 5)
    assert state.view == s.EVOLUTION
    assert (state.evo_stage, state.evo_row) == (1, 0)
    assert state.evo_cursor == 5


def test_evolution_cursor_moves_and_clamps(state: PokedexState):
    open_evolution(state, 4)
    state.handle(s.LEFT)
    assert state.evo_cursor == 4
    for _ in range(3):
        state.handle(s.RIGHT)
    assert state.evo_cursor == 6
    state.handle(s.DOWN)
    assert state.evo_cursor == 6


def test_a_opens_a_member_and_b_returns(state: PokedexState):
    open_evolution(state, 4)
    state.handle(s.RIGHT)
    state.handle(s.A)
    assert state.view == s.DETAIL
    assert state.selected_id == 5


def test_member_not_on_the_card_cannot_be_opened(state: PokedexState):
    open_evolution(state, 133)
    state.handle(s.RIGHT)
    assert state.evo_cursor == 134
    state.handle(s.A)
    assert state.view == s.EVOLUTION


def test_opening_a_member_clears_a_filter_that_hides_it(state: PokedexState):
    open_list(state)
    state.set_filter("flying")
    assert state.open_species(4)
    assert state.type_filter is None
    assert state.selected_id == 4
    assert not state.open_species(999)


def test_no_chain_data(state: PokedexState):
    open_evolution(state, 25)
    assert state.view == s.EVOLUTION
    assert state.evo_cursor is None
    for action in (s.UP, s.DOWN, s.LEFT, s.RIGHT, s.A):
        state.handle(action)
    assert state.view == s.EVOLUTION
    state.handle(s.B)
    assert state.view == s.DETAIL


def test_missing_entry_file():
    state = PokedexState(Dex(ENTRIES), lambda pokemon_id: None)
    open_evolution(state, 4)
    assert state.view == s.EVOLUTION
    assert state.stages == []
