"""Finding Pokémon by name or National Pokédex number."""

import unicodedata
from collections.abc import Iterable

from pokedex.models import Pokemon


def normalize(text: str) -> str:
    """Lower-case letters and digits only: "Mr. Mime" -> "mrmime", "Flabébé" -> "flabebe"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if c.isascii() and c.isalnum()).lower()


def search(pokemon: Iterable[Pokemon], query: str) -> list[Pokemon]:
    """Matches ranked: exact number, then name starts with, name contains, number starts with.

    Ties keep Pokédex order. An empty query matches nothing.
    """
    q = normalize(query)
    if not q:
        return []
    ranked = [(rank, p.id, p) for p in pokemon if (rank := _rank(p, q)) is not None]
    return [p for _, _, p in sorted(ranked, key=lambda item: item[:2])]


def _rank(mon: Pokemon, q: str) -> int | None:
    if q.isdigit() and int(q) == mon.id:
        return 0
    name = normalize(mon.name)
    if name.startswith(q):
        return 1
    if q in name:
        return 2
    if q.isdigit() and (f"{mon.id:03d}".startswith(q) or str(mon.id).startswith(q)):
        return 3
    return None
