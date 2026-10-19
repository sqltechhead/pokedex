"""Record a scripted demo of the UI, with its cries and narration, as an MP4.

    uv run --extra recognize python scripts/demo_video.py [OUTPUT]

Frames are drawn by the real renderer and the sound follows the app's own
rules (cry when an entry opens, narration once the cry ends, everything cut
off when you move on), so the video shows exactly what the device does. Needs
a fetched database with narration, and the dev dependency imageio-ffmpeg.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import wave  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import imageio_ffmpeg  # noqa: E402
import numpy as np  # noqa: E402
import pygame  # noqa: E402

from pokedex import DataPaths, PokedexDB  # noqa: E402
from pokedex.models import Pokemon  # noqa: E402
from pokedex.ui.app import audio_due  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.render import Renderer  # noqa: E402
from pokedex.ui.settings import Settings  # noqa: E402
from pokedex.ui.state import Action, PokedexState, View  # noqa: E402

SIZE = (960, 640)
FPS = 30
RATE = 48000
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
DEFAULT_OUTPUT = Path(__file__).parents[1] / "docs" / "media" / "pokedex-demo.mp4"

# (button, seconds to hold before the next one). None waits for the entry's
# cry and narration to finish, plus a short pause.
SCRIPT: list[tuple[Action | None, float | None]] = [
    (None, 2.0),  # home
    (Action.A, 1.0),  # open the Pokédex
    *[(Action.DOWN, 0.12)] * 24,  # scroll to Pikachu
    (None, 0.8),
    (Action.A, None),  # Pikachu: cry, then narration
    (Action.A, 2.5),  # evolution chain
    (Action.RIGHT, 1.0),  # cursor to Raichu
    (Action.A, 1.5),  # open Raichu...
    (Action.RIGHT, 1.2),  # ...and move on quickly: its sound is cut off
    (Action.RIGHT, None),  # Sandslash plays in full
    (Action.B, 1.0),  # back to the list
    (Action.SELECT, 1.0),  # type filter: Grass
    (Action.SELECT, 1.6),  # Fire
    (Action.DOWN, 0.5),
    (Action.DOWN, 0.6),  # Charizard
    (Action.A, None),
    (Action.A, 3.0),  # Charmander's line
    (Action.B, 0.8),
    (Action.B, 0.8),
    (Action.B, 0.8),  # clear the filter
    (Action.B, 2.0),  # home
]


@dataclass
class Clip:
    start: float
    samples: np.ndarray
    cut_at: float | None = None

    @property
    def end(self) -> float:
        natural = self.start + len(self.samples) / RATE
        return natural if self.cut_at is None else min(natural, self.cut_at)


def decode(path: Path) -> np.ndarray:
    """Mono float audio at RATE. ffmpeg handles cries that are MP3 inside .ogg."""
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


class Soundtrack:
    """The app's EntryAudio rules, recorded onto a timeline instead of a speaker."""

    def __init__(self, paths: DataPaths, settings: Settings) -> None:
        self.paths = paths
        self.settings = settings
        self.clips: list[Clip] = []

    def play(self, mon: Pokemon, at: float) -> float:
        """Start an entry's audio; returns when it finishes."""
        self.stop(at)
        t = at
        for enabled, stored in ((self.settings.cry, mon.cry_path),
                                (self.settings.narration, mon.narration_path)):  # fmt: skip
            if enabled and stored:
                clip = Clip(t, decode(self.paths.resolve(stored)) * self.settings.volume)
                self.clips.append(clip)
                t = clip.end
        return t

    def stop(self, at: float) -> None:
        for clip in self.clips:
            if clip.start < at < clip.end:
                clip.cut_at = at
        self.clips = [c for c in self.clips if c.start < at or c.cut_at is not None]

    def render(self, duration: float) -> np.ndarray:
        mix = np.zeros(int(duration * RATE) + 1, dtype=np.float32)
        for clip in self.clips:
            start = int(clip.start * RATE)
            length = min(int((clip.end - clip.start) * RATE), len(mix) - start)
            fade = min(length, int(0.01 * RATE))  # no click where a sound is cut off
            part = clip.samples[:length].copy()
            if clip.cut_at is not None and fade:
                part[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
            mix[start : start + length] += part
        return np.clip(mix, -1, 1)


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = DataPaths()
    with PokedexDB(paths.db) as db:
        pokemon, chains = db.all(), db.chains()

    pygame.init()
    screen = pygame.display.set_mode(SIZE)
    renderer = Renderer(screen, ImageCache(paths))
    settings = Settings()
    state = PokedexState(pokemon, chains, page_size=renderer.list_rows, settings=settings)
    sound = Soundtrack(paths, settings)

    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "video.mp4"
        encoder = subprocess.Popen(
            [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{SIZE[0]}x{SIZE[1]}", "-r", str(FPS), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
             str(video)],
            stdin=subprocess.PIPE,
        )  # fmt: skip
        assert encoder.stdin is not None
        t = 0.0
        audio_ends = 0.0
        frames = 0
        for action, hold in SCRIPT:
            before = (state.view, state.selected.id if state.selected else None)
            if action is not None:
                state.handle(action)
            if audio_due(before, state):
                audio_ends = sound.play(state.selected, t)
            elif state.view is not View.DETAIL and before[0] is View.DETAIL:
                sound.stop(t)
            if hold is None:
                hold = max(audio_ends - t, 0) + 1.0
            renderer.draw(state)
            frame = pygame.image.tobytes(screen, "RGB")
            target = round((t + hold) * FPS)
            encoder.stdin.write(frame * (target - frames))
            frames = target
            t += hold
        encoder.stdin.close()
        encoder.wait()

        audio = Path(tmp) / "audio.wav"
        with wave.open(str(audio), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes((sound.render(t) * 32767).astype("<i2").tobytes())

        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-i", str(video), "-i", str(audio),
             "-c:v", "copy", "-c:a", "aac", "-ac", "2", "-ar", "44100", "-b:a", "192k", "-shortest",
             "-movflags", "+faststart", str(output)],
            check=True,
        )  # fmt: skip
    pygame.quit()
    print(f"Wrote {output} ({t:.0f} s, {output.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
