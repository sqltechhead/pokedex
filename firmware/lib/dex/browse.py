"""Browse by category: pick values in several categories and the list narrows.

Within one category, picks widen the match (Pink or White); across
categories they narrow it (Pink and Four legs). As picks are made, every
category's counts update to the Pokémon still matching, values with none
left are hidden, and so are categories with nothing left to pick. A
category's own counts ignore its own picks, so its other values stay
available to add.

The categories are worked out on the PC (pokedex-sdcard) into ``cat/``:

    cat/categories.tsv     slug<TAB>label<TAB>number of values
    cat/<slug>.tsv         label<TAB>total number of Pokémon, one value per line
    cat/<slug>.bin         for each Pokémon in index order: a count byte, then
                           that many value numbers (2 bytes, little-endian)
    cat/has.bin            per category, a bit per Pokémon: has any value in it
"""


def _lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [line.rstrip("\r\n") for line in f if line.strip()]
    except OSError:
        return []


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


class Browse:
    def __init__(self, root, dex):
        self.root = root
        self.dex = dex
        self.categories = []
        """(slug, label, number of values), every category on the card."""
        for line in _lines(root + "/categories.tsv"):
            fields = line.split("\t")
            if len(fields) == 3:
                self.categories.append((fields[0], fields[1], int(fields[2])))
        size = (len(dex) + 7) // 8
        has = _read(root + "/has.bin")
        self._has = {}
        """slug -> bitmap of the Pokémon with any value in that category."""
        if len(has) == size * len(self.categories):
            for i, (slug, _, _) in enumerate(self.categories):
                self._has[slug] = has[i * size : (i + 1) * size]
        self.picked = {}
        """slug -> {value number: label} for the values picked in that category."""
        self._matched = {}
        """slug -> index positions matching that category's picks (any of them)."""
        self.positions = None
        """Index positions matching every category picked from, or None if nothing is."""
        self._values_slug = None
        self._values = []
        self._counts = None
        """(slug, counts) for the category last counted; cleared when picks change."""
        self._shown_categories = None

    # The card's data

    def values(self, slug):
        """(label, total number of Pokémon) for each of a category's values."""
        if slug != self._values_slug:
            self._values_slug = slug
            self._values = []  # one category's list in memory at a time
            for line in _lines(f"{self.root}/{slug}.tsv"):
                label, _, count = line.rpartition("\t")
                self._values.append((label, int(count)))
        return self._values

    def _members(self, slug):
        """(index position, [value numbers]) for every Pokémon, from cat/<slug>.bin."""
        data = _read(f"{self.root}/{slug}.bin")
        i = 0
        for pos in range(len(self.dex)):
            if i >= len(data):
                return
            n = data[i]
            ks = [data[i + 1 + 2 * j] | data[i + 2 + 2 * j] << 8 for j in range(n)]
            i += 1 + 2 * n
            yield pos, ks

    # Picking

    def is_picked(self, slug, k):
        return k in self.picked.get(slug, {})

    def toggle(self, slug, k):
        chosen = self.picked.setdefault(slug, {})
        if k in chosen:
            del chosen[k]
        else:
            chosen[k] = self.values(slug)[k][0]
        if chosen:
            self._matched[slug] = {
                pos for pos, ks in self._members(slug) if any(v in chosen for v in ks)
            }
        else:
            del self.picked[slug]
            del self._matched[slug]
        self._changed()

    def clear(self):
        self.picked = {}
        self._matched = {}
        self._changed()

    def _changed(self):
        self.positions = self._others(None)
        self._counts = None
        self._shown_categories = None

    def _others(self, slug):
        """Positions matching every category's picks except slug's, or None for all."""
        result = None
        for other, matched in self._matched.items():
            if other != slug:
                result = set(matched) if result is None else result & matched
        return result

    @property
    def count(self):
        """How many values are picked, across every category."""
        return sum(len(chosen) for chosen in self.picked.values())

    def summary(self, slug):
        """The picked values' labels in one category, e.g. "Pink, White"."""
        return ", ".join(self.picked[slug].values()) if slug in self.picked else ""

    # What to show

    def counts(self, slug):
        """For each of a category's values, how many Pokémon matching the other
        categories' picks have it."""
        if self._counts is None or self._counts[0] != slug:
            base = self._others(slug)
            tally = [0] * len(self.values(slug))
            for pos, ks in self._members(slug):
                if base is None or pos in base:
                    for k in ks:
                        if k < len(tally):
                            tally[k] += 1
            self._counts = (slug, tally)
        return self._counts[1]

    def shown_values(self, slug):
        """Value numbers worth showing: some Pokémon left have them, or they're picked."""
        counts = self.counts(slug)
        return [k for k, n in enumerate(counts) if n or self.is_picked(slug, k)]

    def shown_categories(self):
        """Categories with something left to pick (or with picks of their own)."""
        if self._shown_categories is None:
            self._shown_categories = [c for c in self.categories if self._worth_showing(c[0])]
        return self._shown_categories

    def _worth_showing(self, slug):
        if slug in self.picked or self.positions is None:
            return True
        bits = self._has.get(slug)
        if bits is None:  # no has.bin: count properly
            return any(self.counts(slug))
        return any(bits[pos >> 3] & (1 << (pos & 7)) for pos in self.positions)

    @staticmethod
    def letter_jump(labels, index, step):
        """The next label (or previous, step -1) starting with a different letter."""
        if not labels:
            return 0
        letter = labels[index][:1].upper()
        i = index
        for _ in range(len(labels)):
            i = (i + step) % len(labels)
            first = labels[i][:1].upper()
            if first != letter:
                if step < 0:  # land on the first label with that letter
                    while i and labels[i - 1][:1].upper() == first:
                        i -= 1
                return i
        return index
