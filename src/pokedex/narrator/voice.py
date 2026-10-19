"""Piper voice models: downloading them and speaking text."""

from pathlib import Path

import numpy as np
import requests
from piper import PiperVoice, SynthesisConfig

VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
DEFAULT_VOICE = "en_US-ryan-high"
"""US English, high quality. Its training data is licensed for non-commercial use only."""

# Steadier timing and intonation than Piper's defaults: more like a device reading aloud.
DEVICE_DELIVERY = SynthesisConfig(length_scale=1.05, noise_scale=0.45, noise_w_scale=0.4)


def voice_url(name: str, suffix: str) -> str:
    """``en_US-joe-medium`` lives at ``en/en_US/joe/medium/en_US-joe-medium.onnx``."""
    locale, speaker, quality = name.split("-", 2)
    language = locale.split("_")[0]
    return f"{VOICES_URL}/{language}/{locale}/{speaker}/{quality}/{name}{suffix}"


def ensure_voice(name: str, voices_dir: Path) -> Path:
    """The model's path, downloading it (about 60 MB) the first time."""
    voices_dir.mkdir(parents=True, exist_ok=True)
    model = voices_dir / f"{name}.onnx"
    for path, suffix in ((model, ".onnx"), (voices_dir / f"{name}.onnx.json", ".onnx.json")):
        if not path.exists():
            print(f"Downloading voice {path.name} ...")
            response = requests.get(voice_url(name, suffix), timeout=120)
            response.raise_for_status()
            path.write_bytes(response.content)
    return model


class Speaker:
    def __init__(self, model: Path, *, device: bool = True) -> None:
        self._voice = PiperVoice.load(model)
        self._config = DEVICE_DELIVERY if device else None

    @property
    def sample_rate(self) -> int:
        return self._voice.config.sample_rate

    def speak(self, text: str) -> np.ndarray:
        """Float audio in -1..1 at sample_rate."""
        chunks = [chunk.audio_float_array for chunk in self._voice.synthesize(text, self._config)]
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
