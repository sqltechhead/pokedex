"""Settings, units, screen sleep and button repeat."""

import json

import pytest

from dex import state as s
from dex.settings import ROWS, Settings
from dex.state import MENU, PokedexState
from dex.timing import Repeater, ScreenSleep
from dex.units import format_height, format_weight


def row_of(key: str) -> int:
    return next(i for i, row in enumerate(ROWS) if row[0] == key)


def open_settings(state: PokedexState) -> None:
    state.open_menu(next(i for i, (_, view) in enumerate(MENU) if view == s.SETTINGS))


def test_settings_change_with_dpad_and_a(state: PokedexState):
    open_settings(state)
    state.handle(s.LEFT)  # volume 8 -> 7
    assert state.settings.volume == 7
    state.handle(s.A)  # A doesn't change a slider
    assert state.settings.volume == 7
    state.handle(s.DOWN)
    state.handle(s.A)
    assert state.settings.sound is False
    state.settings_index = row_of("units")
    state.handle(s.RIGHT)
    assert state.settings.units == "imperial"
    state.settings_index = 0
    state.handle(s.UP)
    assert state.settings_index == len(ROWS) - 1  # wrapped from the top
    state.handle(s.B)
    assert state.view == s.HOME


def test_brightness_and_shiny():
    settings = Settings()
    assert settings.backlight == 0.8
    assert settings.adjusted("brightness", -20).brightness == 1  # never fully dark
    assert settings.adjusted("brightness", 5).describe("brightness") == "100%"
    assert settings.shiny is False
    assert settings.adjusted("shiny", 1).shiny is True
    assert Settings({"brightness": 0}).brightness == 8  # out of range: default


def test_volume_stays_in_range():
    settings = Settings({"volume": 9})
    assert settings.adjusted("volume", 5).volume == 10
    assert settings.adjusted("volume", -20).volume == 0
    assert Settings({"volume": 5}).level == 0.5


def test_describe():
    settings = Settings()
    assert settings.describe("volume") == "80%"
    assert settings.describe("sound") == "On"
    assert settings.describe("units") == "Metric"
    assert settings.adjusted("sleep_minutes", -1).describe("sleep_minutes") == "1 min"
    assert Settings({"sleep_minutes": 0}).describe("sleep_minutes") == "Never"


def test_settings_saved_and_loaded(tmp_path):
    path = tmp_path / "settings.json"
    assert Settings.load(path) == Settings()
    changed = Settings().adjusted("units", 1).adjusted("cry", 1)
    assert changed.save(path)
    assert Settings.load(path) == changed


@pytest.mark.parametrize(
    "saved",
    ["not json", "[1, 2]", json.dumps({"volume": 99, "units": "furlongs", "sound": "yes"})],
)
def test_damaged_settings_fall_back_to_defaults(tmp_path, saved: str):
    path = tmp_path / "settings.json"
    path.write_text(saved)
    assert Settings.load(path) == Settings()


def test_save_reports_a_locked_card(tmp_path):
    assert not Settings().save(tmp_path / "missing-folder" / "settings.json")


@pytest.mark.parametrize(
    ("height_dm", "metric", "imperial"),
    [(4, "0.4 m", "1'04\""), (17, "1.7 m", "5'07\""), (10, "1 m", "3'03\"")],
)
def test_height(height_dm: int, metric: str, imperial: str):
    assert format_height(height_dm, "metric") == metric
    assert format_height(height_dm, "imperial") == imperial


@pytest.mark.parametrize(
    ("weight_hg", "metric", "imperial"),
    [(60, "6 kg", "13.2 lbs"), (905, "90.5 kg", "199.5 lbs"), (1, "0.1 kg", "0.2 lbs")],
)
def test_weight(weight_hg: int, metric: str, imperial: str):
    assert format_weight(weight_hg, "metric") == metric
    assert format_weight(weight_hg, "imperial") == imperial


def test_screen_sleep():
    sleep = ScreenSleep(now=0)
    assert not sleep.due(2, 119_999)
    assert sleep.due(2, 120_000)
    assert not sleep.due(0, 10_000_000)  # 0 = never
    sleep.asleep = True
    assert not sleep.due(2, 999_999)
    assert sleep.note_input(1_000_000)  # the waking press
    assert not sleep.asleep
    assert not sleep.note_input(1_000_001)


def test_held_dpad_repeats_other_buttons_dont():
    repeater = Repeater()
    repeater.press(s.DOWN, 0, s.DPAD)
    assert repeater.due(Repeater.DELAY - 1) is None
    assert repeater.due(Repeater.DELAY) == s.DOWN
    assert repeater.due(Repeater.DELAY + 1) is None
    assert repeater.due(Repeater.DELAY + Repeater.INTERVAL) == s.DOWN
    repeater.release(s.DOWN)
    assert repeater.due(10_000) is None

    repeater.press(s.A, 0, s.DPAD)
    assert repeater.due(10_000) is None
