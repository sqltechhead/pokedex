"""The device's own sound effects, synthesised from scratch: no recordings needed.

All original: a start-up jingle, and a chime and a buzz for the quiz. Written
as mono 16-bit WAVs at the same rate as the cries (see audio.SAMPLE_RATE).
"""

import math
import struct
import wave
from pathlib import Path

from pokedex.sdcard.audio import SAMPLE_RATE

Note = tuple[float, float, float]
"""(frequency in Hz, start in seconds, length in seconds)."""


def tone(frequency: float, seconds: float, volume: float = 0.5) -> list[float]:
    """A soft bell-like note: a quick attack, a long fade, a touch of the octave above."""
    n = int(SAMPLE_RATE * seconds)
    attack = int(SAMPLE_RATE * 0.01)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        envelope = min(1.0, i / attack) * math.exp(-3.0 * t / seconds)
        wave_ = math.sin(2 * math.pi * frequency * t) + 0.25 * math.sin(4 * math.pi * frequency * t)
        out.append(volume * envelope * wave_ / 1.25)
    return out


def mix(notes: list[Note], volume: float = 0.5) -> list[float]:
    length = max(start + seconds for _, start, seconds in notes)
    out = [0.0] * int(SAMPLE_RATE * length + 1)
    for frequency, start, seconds in notes:
        offset = int(SAMPLE_RATE * start)
        for i, sample in enumerate(tone(frequency, seconds, volume)):
            out[offset + i] += sample
    return out


def write_wav(samples: list[float], dest: Path) -> None:
    peak = max(1.0, max(abs(s) for s in samples))
    frames = b"".join(struct.pack("<h", int(32767 * 0.9 * s / peak)) for s in samples)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(frames)


def note(name: str) -> float:
    """ "A4" -> 440 Hz. Sharps only ("C#5")."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    pitch, octave = name[:-1], int(name[-1])
    semitones = names.index(pitch) - names.index("A") + 12 * (octave - 4)
    return 440.0 * 2 ** (semitones / 12)


def startup() -> list[float]:
    """A rising five-note run that settles on a held major chord (about 1.3 s)."""
    run = [("G4", 0.0), ("C5", 0.09), ("E5", 0.18), ("G5", 0.27), ("D5", 0.40)]
    notes = [(note(n), start, 0.25) for n, start in run]
    notes += [(note(n), 0.55, 0.75) for n in ("C5", "E5", "G5", "C6")]
    return mix(notes)


def correct() -> list[float]:
    return mix([(note("E5"), 0.0, 0.2), (note("A5"), 0.1, 0.45)])


def wrong() -> list[float]:
    return mix([(note("D4"), 0.0, 0.18), (note("A3"), 0.14, 0.4)])


SOUNDS = {"startup": startup, "correct": correct, "wrong": wrong}


def write_sounds(folder: Path, *, force: bool = False) -> None:
    for name, make in SOUNDS.items():
        dest = folder / f"{name}.wav"
        if force or not dest.exists():
            write_wav(make(), dest)
