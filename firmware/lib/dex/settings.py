"""User settings, changed on the device's settings screen and kept on the SD card."""

import json

# Rows of the settings screen, top to bottom: (setting, label, kind).
ROWS = (
    ("volume", "Volume", "slider"),
    ("sound", "Sound", "switch"),
    ("cry", "Cries", "switch"),
    ("narration", "Read entries aloud", "switch"),
    ("units", "Units", "choice"),
    ("sleep_minutes", "Screen sleep", "choice"),
)
KEY, LABEL, KIND = 0, 1, 2

CHOICES = {
    "units": ("metric", "imperial"),
    "sleep_minutes": (1, 2, 5, 10, 0),
}
DEFAULTS = {
    "volume": 8,
    "sound": True,
    "cry": True,
    "narration": True,
    "units": "metric",
    "sleep_minutes": 2,
}
VOLUME_STEPS = 10
"""Volume is 0-10 rather than a float, so it stays exact on the Pico."""


class Settings:
    def __init__(self, values=None):
        self.values = dict(DEFAULTS)
        for key, value in (values or {}).items():
            if _valid(key, value):
                self.values[key] = value

    def __getattr__(self, key):
        try:
            return self.values[key]
        except KeyError:
            raise AttributeError(key) from None

    def __eq__(self, other):
        return isinstance(other, Settings) and self.values == other.values

    @property
    def level(self):
        """Volume as 0.0-1.0 for the audio mixer."""
        return self.values["volume"] / VOLUME_STEPS

    def adjusted(self, key, delta):
        """A copy with one setting changed: volume steps, switches flip, choices cycle."""
        values = dict(self.values)
        if key == "volume":
            values[key] = min(VOLUME_STEPS, max(0, values[key] + delta))
        elif key in CHOICES:
            options = CHOICES[key]
            values[key] = options[(options.index(values[key]) + delta) % len(options)]
        else:
            values[key] = not values[key]
        return Settings(values)

    def describe(self, key):
        value = self.values[key]
        if key == "volume":
            return f"{value * 100 // VOLUME_STEPS}%"
        if key == "sleep_minutes":
            return "Never" if value == 0 else f"{value} min"
        if value is True or value is False:
            return "On" if value else "Off"
        return value[:1].upper() + value[1:]

    @classmethod
    def load(cls, path):
        """Saved settings, or the defaults if there are none or the file is damaged."""
        try:
            with open(path) as f:
                values = json.load(f)
        except (OSError, ValueError):
            return cls()
        return cls(values if isinstance(values, dict) else None)

    def save(self, path):
        """Returns False if the card couldn't be written (e.g. it is locked)."""
        try:
            with open(path, "w") as f:
                json.dump(self.values, f)
        except OSError:
            return False
        return True


def _valid(key, value):
    if key not in DEFAULTS:
        return False
    if key == "volume":
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10
    if key in CHOICES:
        return value in CHOICES[key]
    return value is True or value is False
