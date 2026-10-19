import os
import subprocess
import threading
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from pokedex.models import BaseStats, Pokemon  # noqa: E402
from pokedex.paths import DataPaths  # noqa: E402
from pokedex.ui.app import run, wait_ms  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.power import Backlight, ScreenSleep, is_raspberry_pi, run_power_action  # noqa: E402
from pokedex.ui.settings import ROWS, Settings  # noqa: E402
from pokedex.ui.sound import EntryAudio  # noqa: E402
from pokedex.ui.state import MENU, Action, PokedexState, ScanPhase, ScanResult, View  # noqa: E402
from pokedex.units import format_height, format_weight  # noqa: E402

STATS = BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)


@pytest.mark.parametrize(
    ("dm", "hg", "metric", "imperial"),
    [
        (4, 60, ("0.4 m", "6 kg"), ("1'04\"", "13.2 lbs")),  # Pikachu
        (17, 905, ("1.7 m", "90.5 kg"), ("5'07\"", "199.5 lbs")),  # Charizard
        (2, 1, ("0.2 m", "0.1 kg"), ("0'08\"", "0.2 lbs")),  # Flabébé-sized
        (145, 9999, ("14.5 m", "999.9 kg"), ("47'07\"", "2204.4 lbs")),  # Eternatus
    ],
)
def test_units(dm, hg, metric, imperial):
    assert (format_height(dm, "metric"), format_weight(hg, "metric")) == metric
    assert (format_height(dm, "imperial"), format_weight(hg, "imperial")) == imperial


def test_choices_cycle_and_describe():
    settings = Settings()
    assert settings.describe("units") == "Metric"
    assert settings.adjusted("units", 1).units == "imperial"
    assert settings.adjusted("units", 2).units == "metric"
    assert settings.adjusted("sleep_minutes", -1).sleep_minutes == 1
    assert Settings(sleep_minutes=0).describe("sleep_minutes") == "Never"
    assert Settings(sleep_minutes=5).describe("sleep_minutes") == "5 min"
    assert Settings(scanner_sensitivity="relaxed").auto_open_confidence < 0.6


def test_old_settings_files_still_load(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"volume": 0.5, "sound": true, "cry": true, "narration": false}')
    assert Settings.load(path) == Settings(volume=0.5, narration=False)


@pytest.fixture
def state() -> PokedexState:
    mons = [
        Pokemon(id=i, name=f"Mon{i}", type1="normal", height_dm=1, weight_hg=1, stats=STATS)
        for i in (1, 25)
    ]
    state = PokedexState(mons)
    state.open_menu([view for _, view in MENU].index(View.SETTINGS))
    return state


def go_to(state: PokedexState, key: str) -> None:
    while ROWS[state.settings_index].key != key:
        state.handle(Action.DOWN)


class TestSettingsScreen:
    def test_shut_down_needs_a_second_press(self, state):
        go_to(state, "shutdown")
        state.handle(Action.A)
        assert state.pending_action == "shutdown"
        assert state.power_request is None
        state.handle(Action.A)
        assert state.power_request == "shutdown"

    def test_moving_or_b_cancels_the_confirmation(self, state):
        go_to(state, "restart")
        state.handle(Action.A)
        state.handle(Action.DOWN)
        assert state.pending_action is None
        state.handle(Action.A)
        state.handle(Action.B)
        assert state.pending_action is None
        assert state.view is View.SETTINGS  # B cancelled, it didn't leave
        state.handle(Action.B)
        assert state.view is View.HOME

    def test_dpad_and_a_change_choices(self, state):
        go_to(state, "units")
        state.handle(Action.A)
        assert state.settings.units == "imperial"
        go_to(state, "scanner_sensitivity")
        state.handle(Action.LEFT)
        assert state.settings.scanner_sensitivity == "strict"

    def test_sensitivity_decides_when_a_match_opens(self, state):
        for sensitivity, opens in (("strict", False), ("relaxed", True)):
            state.settings = Settings(scanner_sensitivity=sensitivity)
            state.open_scanner()
            state.handle(Action.A)
            state.scan_started()
            state.scan_finished([ScanResult(25, 0.5), ScanResult(1, 0.3)])
            assert (state.view is View.DETAIL) is opens
            assert (state.scanner.phase is ScanPhase.CHOOSE) is not opens


class TestPower:
    def test_refuses_off_the_pi(self):
        calls = []
        problem = run_power_action("shutdown", on_pi=False, runner=lambda *a, **k: calls.append(a))
        assert "only work on the Pokédex" in problem
        assert calls == []

    def test_runs_the_command_on_the_pi(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        assert run_power_action("restart", on_pi=True, runner=runner) is None
        assert calls == [["sudo", "-n", "reboot"]]

    def test_reports_a_permission_problem(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, "", "sudo: a password is required\n")

        problem = run_power_action("shutdown", on_pi=True, runner=runner)
        assert problem == "Couldn't shutdown: sudo: a password is required"

    def test_detects_the_pi(self, tmp_path):
        model = tmp_path / "model"
        model.write_text("Raspberry Pi Zero 2 W Rev 1.0\x00")
        assert is_raspberry_pi(model)
        assert not is_raspberry_pi(tmp_path / "missing")

    def test_backlight(self, tmp_path):
        control = tmp_path / "10-0045" / "bl_power"
        control.parent.mkdir()
        control.write_text("0")
        backlight = Backlight(tmp_path)
        backlight.set(False)
        assert control.read_text() == "1"
        backlight.set(True)
        assert control.read_text() == "0"
        Backlight(tmp_path / "none").set(False)  # no backlight control: nothing happens


class TestScreenSleep:
    def test_timing(self):
        sleep = ScreenSleep(now=0)
        assert sleep.seconds_left(2, now=30) == 90
        assert not sleep.due(2, now=119)
        assert sleep.due(2, now=120)
        assert not sleep.due(0, now=10_000)  # never
        sleep.asleep = True
        assert sleep.note_input(now=200) is True  # this press only wakes it
        assert sleep.note_input(now=201) is False

    def test_wait_ms(self, state):
        sleep = ScreenSleep(now=0)
        state.settings = Settings(sleep_minutes=1)
        assert wait_ms(state, sleep, now=59.5) == 501
        state.open_scanner()
        assert wait_ms(state, sleep, now=0) == 66  # the preview redraws sooner
        state.settings = Settings(sleep_minutes=0)
        state.view = View.HOME
        assert wait_ms(state, sleep, now=0) is None


def test_run_sleeps_wakes_and_shuts_down(tmp_path, state):
    """The real event loop with a controllable clock."""
    pygame.init()
    screen = pygame.display.set_mode((480, 320))
    state.settings = Settings(sleep_minutes=1)
    state.view, state.menu_index = View.HOME, 0
    now = [0.0]
    powered = []
    log = []

    def key(k):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0))
        time.sleep(0.15)

    def script():
        time.sleep(0.2)
        now[0] = 61  # a minute passes...
        pygame.event.post(pygame.event.Event(pygame.USEREVENT))  # ...and the loop wakes up
        time.sleep(0.2)
        log.append(("menu before wake", state.menu_index))
        key(pygame.K_DOWN)  # wakes the screen only
        log.append(("menu after wake", state.menu_index))
        key(pygame.K_DOWN)  # now it moves
        log.append(("menu after press", state.menu_index))
        state.open_menu([view for _, view in MENU].index(View.SETTINGS))
        go_to(state, "shutdown")
        key(pygame.K_RETURN)
        key(pygame.K_RETURN)  # confirmed: run() calls power() and returns

    threading.Thread(target=script, daemon=True).start()
    try:
        run(
            screen,
            state,
            ImageCache(DataPaths(tmp_path)),
            EntryAudio(DataPaths(tmp_path)),
            power=lambda action: powered.append(action),
            clock=lambda: now[0],
        )
    finally:
        pygame.quit()
    assert log == [("menu before wake", 0), ("menu after wake", 0), ("menu after press", 1)]
    assert powered == ["shutdown"]
