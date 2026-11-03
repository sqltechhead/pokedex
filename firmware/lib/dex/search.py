"""Finding Pokémon by name or National Pokédex number."""

ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"


def normalize(text):
    """Lower-case ASCII letters and digits only: "Mr. Mime" -> "mrmime".

    Accents are removed on the PC when the SD card is built ("Flabébé" is
    stored with the key "flabebe"), since CircuitPython has no unicodedata.
    """
    return "".join(c for c in text.lower() if c in ALNUM)


def search(dex, query):
    """Index positions of matches, ranked: exact number, then name starts with,
    name contains, number starts with. Ties keep Pokédex order. An empty
    query matches nothing.
    """
    q = normalize(query)
    if not q:
        return []
    number = int(q) if q.isdigit() else None
    ranked = []
    for pos in range(len(dex)):
        rank = _rank(dex.ids[pos], dex.keys[pos], q, number)
        if rank is not None:
            ranked.append((rank, dex.ids[pos], pos))
    ranked.sort()
    return [pos for _, _, pos in ranked]


def _rank(pokemon_id, key, q, number):
    if number == pokemon_id:
        return 0
    if key.startswith(q):
        return 1
    if q in key:
        return 2
    if number is not None and (f"{pokemon_id:03d}".startswith(q) or str(pokemon_id).startswith(q)):
        return 3
    return None
