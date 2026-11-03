"""Every Pokémon's number, name and types, kept in memory for the list and search.

The SD card's ``index.tsv`` has one line per Pokémon:
``id<TAB>name<TAB>search key<TAB>type1<TAB>type2`` (type2 may be empty).
Full entries stay on the card and are read one at a time (see dex.records).

Types are stored as one byte each rather than as strings, which keeps the
whole index to a few tens of KB of the Pico's 520 KB of RAM.
"""

from dex.theme import TYPE_ORDER

NO_TYPE = 255


class Dex:
    def __init__(self, entries=()):
        self.ids = []
        self.names = []
        self.keys = []
        """Names reduced to lower-case letters and digits, for search."""
        self._types = bytearray()
        self._type_names = list(TYPE_ORDER)
        self._positions = {}
        for entry in entries:
            self.add(*entry)

    def __len__(self):
        return len(self.ids)

    def add(self, pokemon_id, name, key, type1, type2=None):
        self._positions[pokemon_id] = len(self.ids)
        self.ids.append(pokemon_id)
        self.names.append(name)
        self.keys.append(key)
        self._types.append(self._type_code(type1))
        self._types.append(self._type_code(type2) if type2 else NO_TYPE)

    def _type_code(self, type_name):
        if type_name not in self._type_names:
            self._type_names.append(type_name)  # a type newer than TYPE_ORDER
        return self._type_names.index(type_name)

    def types(self, pos):
        """The Pokémon's one or two type names."""
        first, second = self._types[2 * pos], self._types[2 * pos + 1]
        if second == NO_TYPE:
            return (self._type_names[first],)
        return (self._type_names[first], self._type_names[second])

    def has_type(self, pos, type_name):
        return type_name in self.types(pos)

    def type_names(self):
        """Types at least one Pokémon has, in canonical order."""
        present = set(self._types)
        return [name for code, name in enumerate(self._type_names) if code in present]

    def position(self, pokemon_id):
        """Where a Pokémon is in the index, or None if it isn't on the card."""
        return self._positions.get(pokemon_id)

    @classmethod
    def load(cls, path):
        dex = cls()
        with open(path, encoding="utf-8") as lines:
            for line in lines:
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) == 5:
                    dex.add(int(fields[0]), fields[1], fields[2], fields[3], fields[4] or None)
        return dex
