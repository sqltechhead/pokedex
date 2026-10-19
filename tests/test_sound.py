import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import wave  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from pokedex.db import PokedexDB  # noqa: E402
from pokedex.models import BaseStats, Pokemon  # noqa: E402
from pokedex.paths import DataPaths  # noqa: E402
from pokedex.ui.app import audio_due  # noqa: E402
from pokedex.ui.settings import Settings  # noqa: E402
from pokedex.ui.sound import EntryAudio  # noqa: E402
from pokedex.ui.state import Action, PokedexState, View  # noqa: E402

STATS = BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)


def make_mon(pid: int, cry_path: str | None = "cries/0001.wav") -> Pokemon:
    return Pokemon(
        id=pid,
        name=f"Mon{pid}",
        type1="normal",
        height_dm=1,
        weight_hg=1,
        stats=STATS,
        cry_path=cry_path,
    )


def snapshot(state: PokedexState) -> tuple[View, int | None]:
    return state.view, state.selected.id if state.selected else None


@pytest.fixture
def state() -> PokedexState:
    return PokedexState([make_mon(1), make_mon(2)], view=View.LIST)


def test_cry_when_opening_and_browsing(state: PokedexState):
    before = snapshot(state)
    state.handle(Action.A)
    assert audio_due(before, state)

    before = snapshot(state)
    state.handle(Action.RIGHT)
    assert audio_due(before, state)


def test_no_cry_when_moving_in_list_or_returning(state: PokedexState):
    before = snapshot(state)
    state.handle(Action.DOWN)
    assert not audio_due(before, state)

    state.handle(Action.A)
    state.handle(Action.A)  # evolution screen
    before = snapshot(state)
    state.handle(Action.B)  # back to the same entry
    assert not audio_due(before, state)


def write_wav(path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(22050)
        f.writeframes(b"\0\0" * int(22050 * seconds))  # silence


@pytest.fixture
def data(tmp_path) -> DataPaths:
    paths = DataPaths(tmp_path)
    for pid in (1, 2):
        write_wav(paths.cries / f"{pid:04d}.wav", 0.5)
        write_wav(paths.narration / f"{pid:04d}.wav", 3.0)
    return paths


def with_narration(pid: int) -> Pokemon:
    mon = make_mon(pid, cry_path=f"cries/{pid:04d}.wav")
    return mon.model_copy(update={"narration_path": f"narration/{pid:04d}.wav"})


@pytest.fixture
def player(data: DataPaths):
    pygame.init()  # the event queue as well as the mixer
    yield EntryAudio(data)
    pygame.quit()


def playing() -> list[float]:
    """Lengths of the sounds playing on any channel, in seconds."""
    channels = [pygame.mixer.Channel(i) for i in range(pygame.mixer.get_num_channels())]
    return [round(c.get_sound().get_length(), 1) for c in channels if c.get_busy()]


def deliver_events(player: EntryAudio) -> None:
    for event in pygame.event.get():
        player.handle_event(event)


def test_cry_first_then_narration(player: EntryAudio):
    assert player.available
    player.play(with_narration(1))
    assert playing() == [0.5]  # the cry

    player._channel.stop()  # as if the cry had finished
    deliver_events(player)
    assert playing() == [3.0]  # now the narration


def test_switching_entries_quickly_never_overlaps(player: EntryAudio):
    """Regression: the old entry's narration used to start over the new cry."""
    player.play(with_narration(1))
    player.play(with_narration(2))
    deliver_events(player)  # includes the FINISHED posted by cutting off entry 1
    assert playing() == [0.5]  # only entry 2's cry
    assert player._channel.get_sound().get_length() == pytest.approx(0.5, abs=0.05)

    player._channel.stop()
    deliver_events(player)
    assert playing() == [3.0]  # entry 2's narration, and nothing of entry 1


def test_stop_drops_the_waiting_narration(player: EntryAudio):
    player.play(with_narration(1))
    player.stop()
    deliver_events(player)
    assert playing() == []


def test_narration_alone_plays_straight_away(player: EntryAudio):
    player.cry = False
    player.play(with_narration(1))
    assert playing() == [3.0]


def test_muted_or_missing_audio_is_silent(player: EntryAudio):
    player.apply(Settings(sound=False))
    player.play(with_narration(1))
    assert playing() == []

    player.apply(Settings())
    player.play(make_mon(2, cry_path=None))
    player.play(make_mon(3, cry_path="cries/missing.ogg"))
    assert playing() == []


def test_cry_paths_in_database(tmp_path):
    with PokedexDB(tmp_path / "pokedex.db") as db:
        db.upsert(make_mon(1, cry_path=None))
        assert db.ids_without_cry() == {1}
        db.set_cry_path(1, "cries/0001.ogg")
        assert db.ids_without_cry() == set()
        assert db.get(1).cry_path == "cries/0001.ogg"
