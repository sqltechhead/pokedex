"""The firmware reading what pokedex-sdcard writes: index, entries and evolution chains."""

from dex import evolution
from dex.index import Dex
from dex.records import Records
from pokedex.models import BaseStats, Evolution, EvolutionChain, Pokemon
from pokedex.sdcard import entries

STATS = BaseStats(hp=45, attack=49, defense=49, sp_attack=65, sp_defense=65, speed=45)


def mon(
    pid: int, name: str, type1: str, type2: str | None = None, chain: int | None = 1
) -> Pokemon:
    return Pokemon(
        id=pid,
        name=name,
        genus="Seed Pokémon",
        type1=type1,
        type2=type2,
        height_dm=7,
        weight_hg=69,
        stats=STATS,
        flavor_text="A strange seed was planted on its back at birth.",
        evolution_chain_id=chain,
    )


POKEMON = [
    mon(2, "Ivysaur", "grass", "poison"),
    mon(1, "Bulbasaur", "grass", "poison"),
    mon(669, "Flabébé", "fairy", chain=None),
]
CHAINS = {
    1: EvolutionChain(
        id=1,
        root_id=1,
        root_name="Bulbasaur",
        evolutions=(
            Evolution(from_id=1, to_id=2, to_name="Ivysaur", method="Lv. 16"),
            Evolution(from_id=2, to_id=3, to_name="Venusaur", method="Lv. 32"),
        ),
    )
}


def write_card(tmp_path) -> Records:
    (tmp_path / "mon").mkdir()
    (tmp_path / "index.tsv").write_text("\n".join(entries.index_lines(POKEMON)) + "\n", "utf-8")
    for p in POKEMON:
        (tmp_path / "mon" / f"{p.id:04d}.json").write_text(entries.entry_json(p, CHAINS), "utf-8")
    return Records(str(tmp_path))


def test_index_round_trip(tmp_path):
    write_card(tmp_path)
    dex = Dex.load(str(tmp_path / "index.tsv"))
    assert dex.ids == [1, 2, 669]  # sorted by number
    assert dex.names == ["Bulbasaur", "Ivysaur", "Flabébé"]
    assert dex.keys[2] == "flabebe"
    assert dex.types(0) == ("grass", "poison")
    assert dex.types(2) == ("fairy",)
    assert dex.position(669) == 2
    assert dex.position(3) is None
    assert dex.type_names() == ["grass", "poison", "fairy"]


def test_unknown_type_is_kept():
    dex = Dex([(1, "Newmon", "newmon", "stellar", None)])
    assert dex.types(0) == ("stellar",)
    assert dex.type_names() == ["stellar"]


def test_entry_round_trip(tmp_path):
    records = write_card(tmp_path)
    entry = records.entry(2)
    assert entry["genus"] == "Seed Pokémon"
    assert entry["stats"] == [45, 49, 49, 65, 65, 45]
    assert entry["height_dm"] == 7
    assert records.entry(669)["chain"] is None
    assert records.entry(999) is None


def test_chain_from_the_card(tmp_path):
    chain = write_card(tmp_path).entry(1)["chain"]
    assert evolution.stages(chain) == [[1], [2], [3]]
    assert evolution.name(chain, 3) == "Venusaur"
    assert evolution.method(chain, 2) == "Lv. 16"
    assert evolution.method(chain, 1) == ""
    assert evolution.stages(None) == []


def test_branching_chain_keeps_parent_order():
    chain = {
        "root": 43,
        "root_name": "Oddish",
        "steps": [[43, 44, "Gloom", "Lv. 21"], [44, 45, "Vileplume", "Leaf Stone"],
                  [44, 182, "Bellossom", "Sun Stone"]],
    }  # fmt: skip
    assert evolution.stages(chain) == [[43], [44], [45, 182]]


def test_damaged_entry_reads_as_missing(tmp_path):
    records = write_card(tmp_path)
    (tmp_path / "mon" / "0001.json").write_text("{not json")
    assert records.entry(1) is None


def test_existing_files(tmp_path):
    records = write_card(tmp_path)
    (tmp_path / "cry").mkdir()
    (tmp_path / "cry" / "0001.wav").write_bytes(b"RIFF")
    assert records.existing("cry", 1, "wav") == f"{tmp_path}/cry/0001.wav"
    assert records.existing("cry", 2, "wav") is None


BODY = (8, 38, 464, 256)


def test_line_layout_is_centred_with_room_for_arrows():
    cells, compact = evolution.layout([[4], [5], [6]], *BODY)
    xs = [cells[i][0] for i in (4, 5, 6)]
    assert compact == set()
    assert all(cells[i][2:] == (100, 116) for i in (4, 5, 6))
    gaps = {xs[1] - xs[0] - 100, xs[2] - xs[1] - 100}
    assert gaps == {82}  # equal gaps, wide enough for "Lv. 16" on the arrow
    assert xs[0] - BODY[0] == BODY[0] + BODY[2] - (xs[2] + 100)  # centred


def test_eevee_branches_become_compact_rows():
    branches = [134, 135, 136, 196, 197, 470, 471, 700]
    cells, compact = evolution.layout([[133], branches], *BODY)
    assert compact == set(branches)
    assert cells[133][2:] == (100, 116)
    assert cells[134][2:] == (156, 32)  # wider, to fit the method beside the name
    rows = [cells[i][1] for i in branches]
    assert rows == sorted(rows) and rows[-1] + 32 <= BODY[1] + BODY[3]
    assert evolution.branched([[133], branches]) == set(branches)


def test_cards_never_leave_the_screen():
    for stages in (
        [[1]],
        [[1], [2]],
        [[1], [2, 3, 4]],
        [[1], [2], [3, 4]],
        [[1], list(range(2, 10))],
    ):
        cells, _ = evolution.layout(stages, *BODY)
        for x, y, w, h in cells.values():
            assert BODY[0] <= x and x + w <= BODY[0] + BODY[2]
            assert BODY[1] <= y and y + h <= BODY[1] + BODY[3]
