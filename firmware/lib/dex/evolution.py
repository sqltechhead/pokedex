"""Evolution chains as stored in an entry's ``chain`` field (see dex.records).

A chain is ``{"root": id, "root_name": name, "steps": [[from, to, to_name, method], ...]}``.
Most are a line; some branch (Eevee, Oddish).
"""


def stages(chain):
    """Species IDs grouped by evolution stage: [[root], [stage 1, ...], ...]."""
    if not chain:
        return []
    steps = chain["steps"]
    result = [[chain["root"]]]
    while True:
        # Children follow their parent's order, so branches stay in rows.
        next_stage = [step[1] for parent in result[-1] for step in steps if step[0] == parent]
        if not next_stage:
            return result
        result.append(next_stage)


CELL_MAX_H = 116
CELL_W = 100
COMPACT_CELL_W = 156
"""Compact rows also show the evolution method beside the name, so they need more width."""
COMPACT_BELOW = 60
"""Cells shorter than this become one-line rows (Eevee's eight branches)."""
MIN_GAP = 56
MAX_GAP = 130
"""Room between columns for the arrows and their labels."""


def layout(stages, x, y, w, h):
    """Where each species' card goes: {species_id: (x, y, w, h)}, plus compact flags.

    A column per stage, centred in the box; branches stack vertically in their
    column. Returns (cells, compact) where compact is the set of species
    drawn as one-line rows.
    """
    n = len(stages)
    heights = [min(CELL_MAX_H, h // len(ids)) for ids in stages]
    widths = [COMPACT_CELL_W if cell_h < COMPACT_BELOW else CELL_W for cell_h in heights]
    gap = min(MAX_GAP, (w - sum(widths)) // (n - 1)) if n > 1 else 0
    if gap < MIN_GAP:
        shrink = (MIN_GAP - gap) * (n - 1) // n + 1
        widths = [width - shrink for width in widths]
        gap = MIN_GAP
    left = x + (w - (sum(widths) + gap * (n - 1))) // 2
    cells = {}
    compact = set()
    for species_ids, cell_w, cell_h in zip(stages, widths, heights):
        top = y + (h - cell_h * len(species_ids)) // 2
        for row, species_id in enumerate(species_ids):
            cells[species_id] = (left, top + row * cell_h, cell_w, cell_h)
            if cell_h < COMPACT_BELOW:
                compact.add(species_id)
        left += cell_w + gap
    return cells, compact


def branched(stages):
    """Species in a stage with siblings: their method goes in the card, not on the arrow,
    since labels on fanned-out arrows would collide."""
    return {species_id for stage in stages if len(stage) > 1 for species_id in stage}


def name(chain, species_id):
    if species_id == chain["root"]:
        return chain["root_name"]
    for step in chain["steps"]:
        if step[1] == species_id:
            return step[2]
    return ""


def method(chain, species_id):
    """How species_id evolves from its parent, e.g. "Lv. 16"; "" for the root."""
    for step in chain["steps"]:
        if step[1] == species_id:
            return step[3]
    return ""
