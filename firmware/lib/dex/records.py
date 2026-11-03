"""Reading a full entry, and finding its pictures and sounds, on the SD card.

Layout written by ``pokedex-sdcard`` on the PC::

    <root>/index.tsv          every Pokémon, one line each (dex.index)
    <root>/mon/0025.json      one entry: genus, size, stats, text, evolution chain
    <root>/art/0025.bmp       official artwork for the entry screen
    <root>/spr/0025.bmp       artwork for the list preview
    <root>/ev72/0025.bmp      evolution card pictures, 72, 44 and 26 px
    <root>/cry/0025.wav       the cry
    <root>/say/0025.wav       the entry read aloud
    <root>/fonts/*.bdf        bitmap fonts

An entry looks like::

    {"id": 25, "genus": "Mouse Pokémon", "height_dm": 4, "weight_hg": 60,
     "stats": [35, 55, 40, 50, 50, 90], "flavor": "When several...",
     "chain": {"root": 172, "root_name": "Pichu",
               "steps": [[172, 25, "Pikachu", "Friendship"], ...]}}

``chain`` is null for Pokémon whose family wasn't fetched.
"""

import json
import os


class Records:
    def __init__(self, root):
        self.root = root
        self._cached_id = None
        self._cached = None

    def entry(self, pokemon_id):
        """The entry as a dict, or None if its file is missing or damaged.

        The last one read is kept, since the entry and evolution screens ask
        for the same one repeatedly.
        """
        if pokemon_id != self._cached_id:
            self._cached_id = pokemon_id
            self._cached = self._read(pokemon_id)
        return self._cached

    def _read(self, pokemon_id):
        try:
            with open(self.file("mon", pokemon_id, "json")) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def file(self, folder, pokemon_id, extension):
        """e.g. file("cry", 25, "wav") -> "<root>/cry/0025.wav"."""
        return f"{self.root}/{folder}/{pokemon_id:04d}.{extension}"

    def existing(self, folder, pokemon_id, extension):
        """The file's path if it is on the card, else None."""
        path = self.file(folder, pokemon_id, extension)
        try:
            os.stat(path)
        except OSError:
            return None
        return path
