"""Layout of the data folder: the fetcher writes it and the UI reads it."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path("data")


@dataclass(frozen=True)
class DataPaths:
    root: Path = DEFAULT_DATA_DIR

    @property
    def db(self) -> Path:
        return self.root / "pokedex.db"

    @property
    def sprites(self) -> Path:
        return self.root / "sprites"

    @property
    def artwork(self) -> Path:
        return self.root / "artwork"

    @property
    def cries(self) -> Path:
        return self.root / "cries"

    @property
    def narration(self) -> Path:
        return self.root / "narration"

    @property
    def voices(self) -> Path:
        """Piper voice models, used only when generating narration."""
        return self.root / "voices"

    def sprite_file(self, pokemon_id: int) -> Path:
        return self.sprites / f"{pokemon_id:04d}.png"

    def artwork_file(self, pokemon_id: int) -> Path:
        return self.artwork / f"{pokemon_id:04d}.png"

    def cry_file(self, pokemon_id: int) -> Path:
        return self.cries / f"{pokemon_id:04d}.ogg"

    def narration_file(self, pokemon_id: int) -> Path:
        return self.narration / f"{pokemon_id:04d}.ogg"

    def relative(self, path: Path) -> str:
        """The form file paths are stored in the database, e.g. ``sprites/0025.png``."""
        return path.relative_to(self.root).as_posix()

    def resolve(self, stored: str) -> Path:
        """Turn a stored path back into a file path."""
        return self.root / stored
