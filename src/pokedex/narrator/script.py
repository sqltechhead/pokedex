"""What the Pokédex says for each entry."""

import re

from pokedex.models import Pokemon

# Spoken respellings for words the voice gets wrong. Matched as whole words,
# case-insensitively. Check a candidate with Piper's phonemizer, e.g.
# PiperVoice.load(model).phonemize("Pokemon").
PRONUNCIATIONS = {
    # "Pokémon" comes out as "PAH-kay-mun"; without the accent it is "POH-kay-mon".
    "pokémon": "Pokemon",
    # "Poké Ball" comes out as "puh-KAY"; "Pokeh" gives "POH-kay".
    "poké": "Pokeh",
}


def narration_text(mon: Pokemon) -> str:
    """ "Pikachu, the Mouse Pokémon. When several of these Pokémon gather, ..." """
    name = speakable_name(mon.name)
    intro = f"{name}, the {mon.genus}." if mon.genus else f"{name}."
    return speakable(f"{intro} {mon.flavor_text}".strip())


def speakable_name(name: str) -> str:
    """Spell out symbols a voice would skip: Nidoran♀ -> "Nidoran female"."""
    name = name.replace("♀", " female").replace("♂", " male")
    return re.sub(r"(?<=[A-Za-z])(?=\d)", " ", name)  # Porygon2 -> Porygon 2


def speakable(text: str) -> str:
    """Rewrite text into the form the voice pronounces correctly."""
    # Older games write POKéMON and other words in capitals, which voices spell out.
    text = re.sub(r"\b[A-ZÉ]{2,}\b", lambda m: m.group(0).capitalize(), text)
    for word, spoken in PRONUNCIATIONS.items():
        text = re.sub(rf"\b{re.escape(word)}\b", spoken, text, flags=re.IGNORECASE)
    return text
