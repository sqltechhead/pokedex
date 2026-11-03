"""Browse by category: the PC writes cat/, the firmware reads and combines picks."""

import pytest

from dex import state as s
from dex.browse import Browse
from dex.index import Dex
from dex.state import MENU, PokedexState
from pokedex.models import BaseStats, Pokemon
from pokedex.sdcard import categories

STATS = BaseStats(hp=50, attack=50, defense=50, sp_attack=50, sp_defense=50, speed=50)


def mon(pid, name, color, shape, height_dm=10, **extra) -> Pokemon:
    return Pokemon(
        id=pid,
        name=name,
        type1="normal",
        height_dm=height_dm,
        weight_hg=100,
        stats=STATS,
        generation=1,
        color=color,
        shape=shape,
        **extra,
    )


POKEMON = [
    mon(1, "Bulbasaur", "green", "quadruped", 7),
    mon(35, "Clefairy", "pink", "humanoid", 6),
    mon(39, "Jigglypuff", "pink", "humanoid", 5),
    mon(58, "Growlithe", "brown", "quadruped", 7),
    mon(150, "Mewtwo", "purple", "upright", 20, legendary=True),
    mon(151, "Mew", "pink", "upright", 4, mythical=True),
    mon(172, "Pichu", "yellow", "quadruped", 3, baby=True),
    mon(225, "Delibird", "red", "wings", 9),
    mon(236, "Tyrogue", "purple", "humanoid", 7, baby=True),
    mon(238, "Smoochum", "pink", "humanoid", 4, baby=True),
]


@pytest.fixture
def card(tmp_path):
    cats = categories.build(POKEMON, {}, {}, {}, {})
    categories.write(cats, [p.id for p in POKEMON], tmp_path / "cat")
    dex = Dex((p.id, p.name, p.name.lower(), p.type1, None, 1) for p in POKEMON)
    return dex, Browse(str(tmp_path / "cat"), dex)


def value(browse: Browse, slug: str, label: str) -> int:
    return [v[0] for v in browse.values(slug)].index(label)


def names(dex: Dex, positions) -> list[str]:
    return sorted(dex.names[p] for p in positions)


def test_categories_and_counts(card):
    _, browse = card
    slugs = [c[0] for c in browse.categories]
    assert slugs[:3] == ["special", "colour", "shape"]
    assert "habitat" not in slugs  # no Pokémon here has one, so it's left out
    assert ("Pink", 4) in browse.values("colour")
    assert browse.values("special") == [
        ("Legendary", 1),
        ("Mythical", 1),
        ("Baby", 3),
        ("Starter", 1),
    ]
    assert browse.values("size")[0] == ("Tiny (under 0.5 m)", 3)


def test_picks_widen_within_a_category_and_narrow_across(card):
    dex, browse = card
    browse.toggle("colour", value(browse, "colour", "Pink"))
    assert names(dex, browse.positions) == ["Clefairy", "Jigglypuff", "Mew", "Smoochum"]
    browse.toggle("colour", value(browse, "colour", "Purple"))  # pink OR purple
    assert len(browse.positions) == 6
    browse.toggle("special", value(browse, "special", "Baby"))  # AND baby
    assert names(dex, browse.positions) == ["Smoochum", "Tyrogue"]
    assert browse.count == 3
    assert browse.summary("colour") == "Pink, Purple"
    browse.toggle("special", value(browse, "special", "Baby"))  # unpicking widens again
    assert len(browse.positions) == 6
    browse.clear()
    assert browse.positions is None and browse.count == 0


def test_letter_jump():
    labels = ["Brown", "Green", "Pink", "Purple", "Red", "Yellow"]
    jump = Browse.letter_jump
    assert labels[jump(labels, 2, 1)] == "Red"  # skips Purple
    assert labels[jump(labels, 2, -1)] == "Green"
    assert labels[jump(labels, 4, -1)] == "Pink"  # the first P


def shown(browse: Browse, slug: str) -> dict[str, int]:
    values, counts = browse.values(slug), browse.counts(slug)
    return {values[k][0]: counts[k] for k in browse.shown_values(slug)}


def test_counts_follow_the_picks(card):
    _, browse = card
    assert shown(browse, "colour")["Pink"] == 4  # nothing picked: totals
    browse.toggle("special", value(browse, "special", "Baby"))
    # Only colours some baby has, counted among the babies.
    assert shown(browse, "colour") == {"Pink": 1, "Purple": 1, "Yellow": 1}
    browse.toggle("colour", value(browse, "colour", "Pink"))
    # A category's own counts ignore its picks, so Purple can still be added.
    assert shown(browse, "colour") == {"Pink": 1, "Purple": 1, "Yellow": 1}
    # ...while the Baby/Legendary list now counts pink Pokémon only.
    assert shown(browse, "special") == {"Mythical": 1, "Baby": 1}


def test_categories_with_nothing_left_are_hidden(card):
    _, browse = card
    slugs = [c[0] for c in browse.shown_categories()]
    assert "special" in slugs and "colour" in slugs
    browse.toggle("colour", value(browse, "colour", "Red"))  # only Delibird
    slugs = [c[0] for c in browse.shown_categories()]
    assert "special" not in slugs  # Delibird isn't legendary, a baby or a starter
    assert "colour" in slugs  # has a pick, so it stays
    assert "shape" in slugs


def test_a_picked_value_stays_listed_even_when_nothing_matches(card):
    _, browse = card
    browse.toggle("colour", value(browse, "colour", "Red"))
    browse.toggle("special", value(browse, "special", "Legendary"))
    assert browse.positions == set()  # red AND legendary: none
    assert "Legendary" in shown(browse, "special")  # still there to unpick


def test_browse_screen_buttons_filter_the_list(card):
    dex, browse = card
    st = PokedexState(dex, browse=browse)
    st.open_menu(next(i for i, (_, view) in enumerate(MENU) if view == s.BROWSE))
    st.handle(s.DOWN)  # Legendary & starters
    st.handle(s.A)
    st.handle(s.DOWN)
    st.handle(s.DOWN)  # Baby
    st.handle(s.A)
    assert names(dex, st.visible) == ["Pichu", "Smoochum", "Tyrogue"]
    st.handle(s.B)
    st.handle(s.DOWN)  # Colour
    st.handle(s.A)
    st.value_index = st.shown_values.index(value(browse, "colour", "Pink"))
    st.handle(s.A)
    assert names(dex, st.visible) == ["Smoochum"]
    st.handle(s.B)
    st.browse_index = 0
    st.handle(s.A)  # Show
    assert st.view == s.LIST and st.filtered
    st.handle(s.B)  # clears every filter
    assert len(st.visible) == len(POKEMON) and browse.count == 0


def test_type_filter_combines_with_picks(card):
    dex, browse = card
    st = PokedexState(dex, browse=browse)
    browse.toggle("colour", value(browse, "colour", "Pink"))
    st.set_filter("normal")
    assert len(st.visible) == 4
    st.set_filter("fire")
    assert st.visible == []


def test_no_categories_on_the_card(tmp_path):
    dex = Dex([(1, "Bulbasaur", "bulbasaur", "grass", "poison", 1)])
    st = PokedexState(dex, browse=Browse(str(tmp_path / "missing"), dex))
    st.view = s.BROWSE
    for action in (s.UP, s.DOWN, s.A, s.SELECT):
        st.handle(action)
    assert st.view == s.BROWSE
    st.handle(s.B)
    assert st.view == s.HOME
