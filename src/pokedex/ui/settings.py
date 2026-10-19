"""User settings, changed on the device's settings screen and kept between runs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pokedex.units import Units

Sensitivity = Literal["strict", "normal", "relaxed"]
RowKind = Literal["slider", "switch", "choice", "action"]


@dataclass(frozen=True)
class Row:
    key: str
    """A Settings field, or for actions the action's name."""
    label: str
    kind: RowKind


# Rows of the settings screen, top to bottom.
ROWS: tuple[Row, ...] = (
    Row("volume", "Volume", "slider"),
    Row("sound", "Sound", "switch"),
    Row("cry", "Cries", "switch"),
    Row("narration", "Read entries aloud", "switch"),
    Row("units", "Units", "choice"),
    Row("sleep_minutes", "Screen sleep", "choice"),
    Row("scanner_sensitivity", "Scanner sensitivity", "choice"),
    Row("rotate_camera", "Camera upside down", "switch"),
    Row("restart", "Restart", "action"),
    Row("shutdown", "Shut down", "action"),
)
CHOICES: dict[str, tuple[object, ...]] = {
    "units": ("metric", "imperial"),
    "sleep_minutes": (1, 2, 5, 10, 0),
    "scanner_sensitivity": ("strict", "normal", "relaxed"),
}
AUTO_OPEN_CONFIDENCE: dict[Sensitivity, float] = {"strict": 0.85, "normal": 0.6, "relaxed": 0.3}
"""How sure a picture match must be to open its entry without asking."""
VOLUME_STEP = 0.1


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    volume: float = Field(default=0.8, ge=0, le=1)
    sound: bool = True
    cry: bool = True
    narration: bool = True
    units: Units = "metric"
    sleep_minutes: int = 2
    """Idle minutes before the screen sleeps; 0 never sleeps."""
    scanner_sensitivity: Sensitivity = "normal"
    rotate_camera: bool = False

    @property
    def auto_open_confidence(self) -> float:
        return AUTO_OPEN_CONFIDENCE[self.scanner_sensitivity]

    def adjusted(self, key: str, delta: int) -> "Settings":
        """A copy with one setting changed: volume steps, switches flip, choices cycle."""
        if key == "volume":
            volume = round(min(1.0, max(0.0, self.volume + delta * VOLUME_STEP)), 2)
            return self.model_copy(update={"volume": volume})
        if key in CHOICES:
            options = CHOICES[key]
            current = options.index(getattr(self, key))
            return self.model_copy(update={key: options[(current + delta) % len(options)]})
        return self.model_copy(update={key: not getattr(self, key)})

    def describe(self, key: str) -> str:
        value = getattr(self, key)
        if key == "volume":
            return f"{round(value * 100)}%"
        if key == "sleep_minutes":
            return "Never" if value == 0 else f"{value} min"
        if isinstance(value, bool):
            return "On" if value else "Off"
        return str(value).capitalize()

    @classmethod
    def load(cls, path: Path) -> "Settings":
        """Saved settings, or the defaults if there are none or the file is damaged."""
        try:
            return cls.model_validate_json(path.read_text())
        except (FileNotFoundError, ValidationError):
            return cls()

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2))
