"""The "device" voice effect: makes a natural voice sound like it comes from a gadget."""

import numpy as np
from scipy.signal import butter, sosfilt

LEAD_IN_SECONDS = 0.35
"""Silence before the voice, so it does not start the instant the cry ends."""


def device_effect(audio: np.ndarray, rate: int) -> np.ndarray:
    """Small-speaker tone, a metallic resonance and a faint synthetic shimmer.

    Takes and returns float audio in -1..1. Each stage is gentle so the words
    stay clear; adjust the numbers here to taste.
    """
    # A small speaker: no deep bass, softened top end.
    voice = sosfilt(butter(2, [280, 5200], btype="bandpass", fs=rate, output="sos"), audio)
    # Metallic resonance: blend in a copy delayed by a few milliseconds (comb filter).
    delay = int(rate * 0.0045)
    metallic = voice.copy()
    metallic[delay:] += 0.4 * voice[:-delay]
    # Ring modulation, mixed low: adds the electronic edge without a robot buzz.
    t = np.arange(len(metallic)) / rate
    ring = metallic * np.sin(2 * np.pi * 110 * t)
    return 0.8 * metallic + 0.2 * ring


def finish(audio: np.ndarray, rate: int) -> np.ndarray:
    """Normalise to a consistent loudness and add the lead-in silence."""
    peak = np.max(np.abs(audio)) if audio.size else 0.0
    if peak > 0:
        audio = audio * (0.9 / peak)
    return np.concatenate([np.zeros(int(rate * LEAD_IN_SECONDS), dtype=audio.dtype), audio])
