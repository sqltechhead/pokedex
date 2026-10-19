"""Screen sleep, the backlight, and shutting the device down safely."""

import subprocess
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

POWER_COMMANDS = {
    # -n: fail rather than wait for a password nobody can type on a handheld.
    "shutdown": ["sudo", "-n", "shutdown", "-h", "now"],
    "restart": ["sudo", "-n", "reboot"],
}
MODEL_FILE = Path("/proc/device-tree/model")


def is_raspberry_pi(model_file: Path = MODEL_FILE) -> bool:
    try:
        return "Raspberry Pi" in model_file.read_text(errors="ignore")
    except OSError:
        return False


def run_power_action(
    action: str,
    *,
    on_pi: bool | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str | None:
    """Shut down or restart the Pi; returns a problem to show, or None if it's happening.

    Anywhere other than a Raspberry Pi this refuses, so testing the menu on a
    laptop never turns the laptop off.
    """
    if not (is_raspberry_pi() if on_pi is None else on_pi):
        return "Shut down and restart only work on the Pokédex itself."
    try:
        result = runner(POWER_COMMANDS[action], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Couldn't {action}: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        return f"Couldn't {action}: {detail[-1] if detail else 'permission denied'}"
    return None


class Backlight:
    """Turns the screen's backlight off while asleep, where the display allows it.

    Uses the kernel's backlight control (/sys/class/backlight/*/bl_power).
    Screens without one, or without permission to write it, just show black.
    """

    def __init__(self, root: Path = Path("/sys/class/backlight")) -> None:
        self._controls = sorted(root.glob("*/bl_power")) if root.exists() else []

    def set(self, on: bool) -> None:
        for control in self._controls:
            with suppress(OSError):  # no permission: the screen just shows black
                control.write_text("0" if on else "1")  # 0 = powered, 1 = off


class ScreenSleep:
    """Tracks idle time; the app blanks the screen when it is due."""

    def __init__(self, now: float) -> None:
        self.asleep = False
        self._last_input = now

    def note_input(self, now: float) -> bool:
        """Record a button press; True if it woke the screen (and should do nothing else)."""
        self._last_input = now
        if self.asleep:
            self.asleep = False
            return True
        return False

    def due(self, minutes: int, now: float) -> bool:
        return not self.asleep and minutes > 0 and now - self._last_input >= minutes * 60

    def seconds_left(self, minutes: int, now: float) -> float | None:
        """Until the screen sleeps; None if it never will (or already has)."""
        if self.asleep or minutes <= 0:
            return None
        return max(0.0, minutes * 60 - (now - self._last_input))
