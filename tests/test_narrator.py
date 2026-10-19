import pytest

from pokedex.models import BaseStats, Pokemon
from pokedex.narrator.script import narration_text, speakable, speakable_name

STATS = BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)


def make_mon(name: str, genus: str | None, flavor: str) -> Pokemon:
    return Pokemon(
        id=1,
        name=name,
        genus=genus,
        type1="normal",
        height_dm=1,
        weight_hg=1,
        stats=STATS,
        flavor_text=flavor,
    )


def test_narration_text():
    mon = make_mon("Pikachu", "Mouse Pokémon", "When several of these POKéMON gather.")
    assert narration_text(mon) == (
        "Pikachu, the Mouse Pokemon. When several of these Pokemon gather."
    )


def test_narration_without_genus():
    assert narration_text(make_mon("Missingno", None, "")) == "Missingno."


@pytest.mark.parametrize(
    ("name", "spoken"),
    [
        ("Nidoran♀", "Nidoran female"),
        ("Nidoran♂", "Nidoran male"),
        ("Porygon2", "Porygon 2"),
        ("Mr. Mime", "Mr. Mime"),
    ],
)
def test_speakable_name(name, spoken):
    assert speakable_name(name) == spoken


def test_capitalised_words_are_not_spelled_out():
    assert speakable("It uses PSYCHIC power. A TRAINER saw it.") == (
        "It uses Psychic power. A Trainer saw it."
    )


def test_voice_url():
    pytest.importorskip("piper")
    from pokedex.narrator.voice import voice_url

    assert voice_url("en_GB-alan-medium", ".onnx") == (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_GB/alan/medium/en_GB-alan-medium.onnx"
    )


def test_device_effect_and_finish():
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    from pokedex.narrator.effects import LEAD_IN_SECONDS, device_effect, finish

    rate = 22050
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)
    processed = finish(device_effect(tone, rate), rate)
    lead_in = int(rate * LEAD_IN_SECONDS)
    assert len(processed) == rate + lead_in
    assert not processed[:lead_in].any()
    assert np.max(np.abs(processed)) == pytest.approx(0.9)


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("Pokémon", "Pokemon"),
        ("POKéMON", "Pokemon"),
        ("a Pokémon's tail", "a Pokemon's tail"),
        ("a POKé Ball", "a Pokeh Ball"),
        ("Poké Ball", "Pokeh Ball"),
    ],
)
def test_pokemon_pronunciation(text, spoken):
    assert speakable(text) == spoken
