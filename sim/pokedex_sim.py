"""Run the Pico firmware on a PC, in a 480x320 window.

    uv run --group sim python sim/pokedex_sim.py

The firmware's own code (firmware/lib/dex) runs unchanged on Adafruit's
desktop version of displayio. Only the hardware is swapped out:

- the screen is a pygame window,
- the keyboard is the buttons (arrows, Z/Enter = A, X/Backspace = B,
  Tab = SELECT, Space = START, Q/E = L/R shoulders),
- sound plays through the computer's speakers,
- build/sd/ is the SD card (make it with ``uv run pokedex-sdcard``).

It shows the layout and behaviour, not the real speed: the SPI screen redraws
far slower than a window, and the PC has far more memory than the Pico.

    pokedex_sim.py                      # play with it
    pokedex_sim.py --shots out/         # click through a tour, saving a PNG per step
"""

import argparse
import contextlib
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware" / "lib"))

import pygame  # noqa: E402
from blinka_displayio_pygamedisplay import PyGameDisplay  # noqa: E402

from dex import state  # noqa: E402

KEYS = {
    pygame.K_UP: state.UP,
    pygame.K_DOWN: state.DOWN,
    pygame.K_LEFT: state.LEFT,
    pygame.K_RIGHT: state.RIGHT,
    pygame.K_z: state.A,
    pygame.K_RETURN: state.A,
    pygame.K_x: state.B,
    pygame.K_BACKSPACE: state.B,
    pygame.K_ESCAPE: state.B,
    pygame.K_TAB: state.SELECT,
    pygame.K_SPACE: state.START,
    pygame.K_q: state.L,
    pygame.K_e: state.R,
}
BUTTON_ACTIONS = tuple(range(10))
"""Simulated button numbers are the actions themselves."""

# A tour for --shots: (button, screenshot name or None).
TOUR = (
    (None, "home"),
    (state.A, "list"),
    *((state.DOWN, None),) * 4,
    (state.DOWN, "list-scrolled"),
    (state.A, "entry"),
    (state.A, "evolution"),
    (state.B, None),
    (state.B, None),
    (state.R, None),
    (state.R, "list-fire"),
    (state.B, None),
    *((state.DOWN, None),) * 128,
    (state.DOWN, "list-eevee"),
    (state.A, None),
    (state.A, "evolution-eevee"),
    (state.B, None),
    (state.B, None),
    (state.B, None),
    (state.DOWN, None),
    (state.A, None),
    (state.RIGHT, None),
    (state.A, None),  # types B
    (state.DOWN, None),
    (state.DOWN, None),
    (state.LEFT, None),
    (state.A, "search"),  # types U
    (state.SELECT, "search-results"),
    (state.A, "entry-from-search"),
    (state.SELECT, None),  # replay
    *((state.B, None),) * 5,  # entry, results, delete U, delete B, home
    (state.DOWN, None),
    (state.A, None),
    (state.DOWN, None),
    (state.DOWN, None),
    (state.DOWN, None),
    (state.DOWN, "settings"),
    (state.B, None),
    (state.UP, None),
    (state.A, None),  # search again, with the cursor still on U
    (state.DOWN, None),
    *((state.RIGHT, None),) * 4,
    (state.A, None),  # types 4
    (state.LEFT, None),
    (state.A, None),  # types 3
    (state.SELECT, None),
    (state.A, None),  # #043 Oddish
    (state.A, "evolution-oddish"),
    (state.START, "menu-from-evolution"),
)


class Event:
    def __init__(self, key_number, pressed):
        self.key_number = key_number
        self.pressed = pressed
        self.released = not pressed


class Events:
    def __init__(self, source):
        self._source = source

    def get(self):
        return self._source()


class KeyboardButtons:
    """keypad.Keys from the keyboard, or from a scripted tour."""

    def __init__(self, script=None):
        self._pending = []
        self._script = list(script) if script is not None else None
        self._between_steps = False
        self.events = Events(self._next)

    def _next(self):
        if self._script is not None:
            return self._scripted()
        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                raise SystemExit
            if event.type in (pygame.KEYDOWN, pygame.KEYUP) and event.key in KEYS:
                self._pending.append(Event(KEYS[event.key], event.type == pygame.KEYDOWN))
        return self._pending.pop(0) if self._pending else None

    def _scripted(self):
        pygame.event.pump()
        if self._pending:
            return self._pending.pop(0)
        if self._between_steps:  # let the app redraw before the next step
            self._between_steps = False
            return None
        self._between_steps = True
        if not self._script:
            raise SystemExit
        action, name = self._script.pop(0)
        Shots.next_name = name
        if action is None:
            Shots.save_now()
            return None
        self._pending.append(Event(action, False))
        return Event(action, True)


class Shots:
    folder = None
    next_name = None
    display = None

    @classmethod
    def save_now(cls):
        if cls.folder and cls.next_name:
            pygame.image.save(
                pygame.display.get_surface(), str(cls.folder / f"{cls.next_name}.png")
            )
            print(f"saved {cls.next_name}.png")
            cls.next_name = None


class SimDisplay(PyGameDisplay):
    def refresh(self, *args, **kwargs):
        result = super().refresh(*args, **kwargs)
        Shots.save_now()
        return result


class Backlight:
    def __init__(self, screen):
        pass

    def set(self, on):
        if not on:  # show the screen as off, as the real backlight would
            pygame.display.get_surface().fill((0, 0, 0))
            pygame.display.flip()


class EntryAudio:
    """dex.audio.EntryAudio on the computer's speakers: cry, then narration."""

    def __init__(self, output, records):
        self._records = records
        self._channel = None
        self._next = None
        self.enabled = self.cry = self.narration = True
        self.level = 0.8
        try:
            pygame.mixer.init()
            self._channel = pygame.mixer.Channel(0)
        except pygame.error:
            print("No sound device: running silently.")

    def play(self, pokemon_id):
        self.stop()
        if not self.enabled or self._channel is None:
            return
        paths = []
        if self.cry:
            paths.append(self._records.existing("cry", pokemon_id, "wav"))
        if self.narration:
            paths.append(self._records.existing("say", pokemon_id, "wav"))
        paths = [p for p in paths if p]
        if paths:
            self._start(paths[0])
            self._next = paths[1] if len(paths) > 1 else None

    def poll(self):
        if self._channel is None or self._channel.get_busy():
            return
        if self._next:
            path, self._next = self._next, None
            self._start(path)

    def stop(self):
        self._next = None
        if self._channel is not None:
            self._channel.stop()

    def apply(self, settings):
        self.level = settings.level
        self.enabled = settings.sound
        self.cry = settings.cry
        self.narration = settings.narration
        if not self.enabled:
            self.stop()

    def _start(self, path):
        sound = pygame.mixer.Sound(path)
        sound.set_volume(self.level)
        self._channel.play(sound)


class Battery:
    volts_now = 3.9

    def volts(self):
        return self.volts_now


def install_fakes(card: Path, script) -> None:
    """Swap dex.hardware and dex.audio for simulated ones before dex.app imports them."""
    import dex

    hardware = types.ModuleType("dex.hardware")
    hardware.SD_MOUNT = str(card)
    hardware.BUTTON_ACTIONS = BUTTON_ACTIONS
    hardware.display = lambda: SimDisplay(width=480, height=320, caption="Pokédex (Pico sim)")

    def mount_sd():
        if not (card / "pokedex" / "index.tsv").exists():
            raise OSError("no card")

    hardware.mount_sd = mount_sd
    hardware.buttons = lambda: KeyboardButtons(script)
    hardware.audio_out = lambda: None
    hardware.Backlight = Backlight
    hardware.Battery = Battery
    sys.modules["dex.hardware"] = dex.hardware = hardware

    audio = types.ModuleType("dex.audio")
    audio.EntryAudio = EntryAudio
    sys.modules["dex.audio"] = dex.audio = audio


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--card", type=Path, default=ROOT / "build" / "sd", help="the SD card folder"
    )
    parser.add_argument(
        "--battery", type=float, default=3.9, help="battery volts to show (below 3.45 is low)"
    )
    parser.add_argument("--shots", type=Path, help="run the tour and save screenshots here")
    args = parser.parse_args()
    if not (args.card / "pokedex" / "index.tsv").exists():
        print(f"No SD card folder at {args.card}. Run `uv run pokedex-sdcard` first.")
        return 1
    script = None
    if args.shots:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        args.shots.mkdir(parents=True, exist_ok=True)
        Shots.folder = args.shots
        script = TOUR
    Battery.volts_now = args.battery
    install_fakes(args.card, script)

    from dex import app

    with contextlib.suppress(SystemExit):  # closing the window, or the end of the tour
        app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
