"""Browse categories: every way to group the Pokémon, worked out on the PC.

The Pico reads them from ``cat/`` on the card (see firmware/lib/dex/browse.py)::

    cat/categories.tsv     slug<TAB>label<TAB>number of values, one category per line
    cat/colour.tsv         label<TAB>number of Pokémon, one value per line
    cat/colour.bin         each Pokémon's values in that category (see write_members)
    cat/has.bin            per category, a bit per Pokémon: has any value in it

Pokémon are in index.tsv order (by Pokédex number), so the Pico can count
any category's values among the current matches with one file read.
"""

import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pokedex.models import Ability, EvolutionChain, Move, Pokemon
from pokedex.sdcard.entries import TypeChart, matchups

STARTERS = frozenset(
    (1, 4, 7, 152, 155, 158, 252, 255, 258, 387, 390, 393, 495, 498, 501)
    + (650, 653, 656, 722, 725, 728, 810, 813, 816, 906, 909, 912)
)
"""Each region's three first-partner Pokémon (no PokéAPI field for this)."""

REGIONS = ("Kanto", "Johto", "Hoenn", "Sinnoh", "Unova", "Kalos", "Alola", "Galar", "Paldea")
SHAPES = {
    "ball": "Head only",
    "squiggle": "Snake-like",
    "fish": "Fish",
    "arms": "Head and arms",
    "blob": "Blob",
    "upright": "Upright with a tail",
    "legs": "Head and legs",
    "quadruped": "Four legs",
    "wings": "Wings",
    "tentacles": "Tentacles",
    "heads": "Several heads",
    "humanoid": "Humanoid",
    "bug-wings": "Bug with wings",
    "armor": "Armoured bug",
}
EGG_GROUPS = {
    "ground": "Field",
    "plant": "Grass",
    "humanshape": "Human-Like",
    "indeterminate": "Amorphous",
    "no-eggs": "Undiscovered",
    "water1": "Water 1",
    "water2": "Water 2",
    "water3": "Water 3",
}
HABITATS = {"waters-edge": "Water's Edge"}
# (label, upper limit) bands; the last has no limit.
SIZES = (
    ("Tiny (under 0.5 m)", 5),
    ("Small (0.5 to 1 m)", 10),
    ("Medium (1 to 2 m)", 20),
    ("Large (2 to 5 m)", 50),
    ("Giant (5 m and over)", None),
)
WEIGHTS = (
    ("Featherweight (under 1 kg)", 10),
    ("Light (1 to 10 kg)", 100),
    ("Medium (10 to 100 kg)", 1000),
    ("Heavy (100 to 500 kg)", 5000),
    ("Huge (500 kg and over)", None),
)
TOP = 20
"""How many make each "Top 20" stat list."""


def readable(slug: str, names: Mapping[str, str] | None = None) -> str:
    """ "rough-terrain" -> "Rough Terrain", unless names gives a better one."""
    if names and slug in names:
        return names[slug]
    return slug.replace("-", " ").title()


@dataclass
class Category:
    slug: str
    label: str
    values: dict[str, list[int]] = field(default_factory=dict)
    """Value label -> Pokédex numbers, in the order shown."""
    sort: bool = True
    """Alphabetical; fixed-order categories (sizes, regions...) keep theirs."""

    def add(self, label: str, pokemon_id: int) -> None:
        self.values.setdefault(label, []).append(pokemon_id)

    def ordered(self) -> list[tuple[str, list[int]]]:
        items = [(label, sorted(ids)) for label, ids in self.values.items() if ids]
        return sorted(items, key=lambda item: item[0].lower()) if self.sort else items


def band(value: int, bands: tuple[tuple[str, int | None], ...]) -> str:
    return next(label for label, limit in bands if limit is None or value < limit)


def build(
    pokemon: Iterable[Pokemon],
    chains: Mapping[int, EvolutionChain],
    moves: Mapping[int, Move],
    abilities: Mapping[int, Ability],
    chart: TypeChart,
) -> list[Category]:
    """Every category, in the order the device lists them."""
    pokemon = sorted(pokemon, key=lambda p: p.id)
    cats = [
        Category("special", "Legendary & starters", sort=False),
        Category("colour", "Colour"),
        Category("shape", "Shape"),
        Category("size", "Size", sort=False),
        Category("weight", "Weight", sort=False),
        Category("type", "Type"),
        Category("region", "Region", sort=False),
        Category("kind", "Species category"),
        Category("habitat", "Habitat (Gen 1-3)"),
        Category("evolution", "Evolution", sort=False),
        Category("weak", "Weak to"),
        Category("resists", "Resists"),
        Category("immune", "Not affected by"),
        Category("stats", "Top 20", sort=False),
        Category("ability", "Ability"),
        Category("move", "Learns move"),
        Category("egg", "Egg group"),
    ]
    by_slug = {c.slug: c for c in cats}
    # Fixed orders, so empty categories still come out in this order.
    for label in ("Legendary", "Mythical", "Baby", "Starter"):
        by_slug["special"].values[label] = []
    for label, _ in SIZES:
        by_slug["size"].values[label] = []
    for label, _ in WEIGHTS:
        by_slug["weight"].values[label] = []
    for label in REGIONS:
        by_slug["region"].values[label] = []
    for label in ("Doesn't evolve", "Can still evolve", "Fully evolved", "Branching family"):
        by_slug["evolution"].values[label] = []

    for mon in pokemon:
        pid = mon.id

        def add(slug: str, label: str, pid: int = pid) -> None:
            by_slug[slug].add(label, pid)

        for flag, label in ((mon.legendary, "Legendary"), (mon.mythical, "Mythical")):
            if flag:
                add("special", label)
        if mon.baby:
            add("special", "Baby")
        if pid in STARTERS:
            add("special", "Starter")
        if mon.color:
            add("colour", readable(mon.color))
        if mon.shape:
            add("shape", readable(mon.shape, SHAPES))
        add("size", band(mon.height_dm, SIZES))
        add("weight", band(mon.weight_hg, WEIGHTS))
        for type_name in mon.types:
            add("type", readable(type_name))
        if mon.generation:
            add("region", REGIONS[mon.generation - 1])
        if mon.genus:
            add("kind", mon.genus)
        if mon.habitat:
            add("habitat", readable(mon.habitat, HABITATS))
        for label in evolution_labels(mon, chains):
            add("evolution", label)
        if chart:
            groups = matchups(mon.types, chart)
            for slug, keys in (
                ("weak", ("4", "2")),
                ("resists", ("0.5", "0.25")),
                ("immune", ("0",)),
            ):
                for key in keys:
                    for type_name in groups[key]:
                        add(slug, readable(type_name))
        for a in mon.abilities:
            if a.ability_id in abilities:
                add("ability", abilities[a.ability_id].name)
        for name in {moves[m.move_id].name for m in mon.level_moves if m.move_id in moves}:
            add("move", name)
        for group in mon.egg_groups:
            add("egg", readable(group, EGG_GROUPS))

    stats: tuple[tuple[str, Callable[[Pokemon], int]], ...] = (
        ("HP", lambda p: p.stats.hp),
        ("Attack", lambda p: p.stats.attack),
        ("Defense", lambda p: p.stats.defense),
        ("Sp. Atk", lambda p: p.stats.sp_attack),
        ("Sp. Def", lambda p: p.stats.sp_defense),
        ("Speed", lambda p: p.stats.speed),
        ("Base stat total", lambda p: p.stats.total),
    )
    for label, stat in stats:
        best = sorted(pokemon, key=lambda p: (-stat(p), p.id))[:TOP]
        by_slug["stats"].values[label] = [p.id for p in best]
    return [c for c in cats if any(c.values.values())]


def evolution_labels(mon: Pokemon, chains: Mapping[int, EvolutionChain]) -> list[str]:
    chain = chains.get(mon.evolution_chain_id) if mon.evolution_chain_id else None
    if chain is None:
        return []
    stages = chain.stages()
    if len(stages) == 1:
        return ["Doesn't evolve"]
    labels = []
    if any(e.from_id == mon.id for e in chain.evolutions):
        labels.append("Can still evolve")
    else:
        labels.append("Fully evolved")
    if any(len(stage) > 1 for stage in stages):
        labels.append("Branching family")
    return labels


def write(categories: list[Category], pokemon_ids: list[int], folder: Path) -> int:
    """Write the cat/ folder for Pokémon in this order; returns the number of values."""
    folder.mkdir(parents=True, exist_ok=True)
    position = {pid: i for i, pid in enumerate(pokemon_ids)}
    lines = []
    has = bytearray()
    written = 0
    for cat in categories:
        values = cat.ordered()
        lines.append(f"{cat.slug}\t{cat.label}\t{len(values)}")
        rows = [f"{label}\t{len(ids)}" for label, ids in values]
        (folder / f"{cat.slug}.tsv").write_text("\n".join(rows) + "\n", "utf-8")
        members: list[list[int]] = [[] for _ in pokemon_ids]
        for k, (_, ids) in enumerate(values):
            for pid in ids:
                if pid in position:
                    members[position[pid]].append(k)
        (folder / f"{cat.slug}.bin").write_bytes(write_members(members))
        bits = bytearray((len(pokemon_ids) + 7) // 8)
        for i, ks in enumerate(members):
            if ks:
                bits[i // 8] |= 1 << (i % 8)
        has += bits
        if (folder / cat.slug).is_dir():  # the old one-file-per-value layout
            shutil.rmtree(folder / cat.slug)
        written += len(values)
    (folder / "categories.tsv").write_text("\n".join(lines) + "\n", "utf-8")
    (folder / "has.bin").write_bytes(bytes(has))
    return written


def write_members(members: list[list[int]]) -> bytes:
    """For each Pokémon: a count byte, then that many value numbers as 2-byte little-endian."""
    out = bytearray()
    for ks in members:
        out.append(len(ks))
        for k in ks:
            out += k.to_bytes(2, "little")
    return bytes(out)
