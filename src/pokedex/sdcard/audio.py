"""Cries and narration as plain WAV files the Pico's audio mixer can stream."""

import subprocess
import wave
from pathlib import Path

SAMPLE_RATE = 22050
"""Must match AUDIO_RATE in firmware/pins.py."""


def ffmpeg_exe() -> str:
    """The ffmpeg bundled with imageio-ffmpeg, so nothing extra needs installing."""
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def to_wav(source: Path, dest: Path, ffmpeg: str | None = None) -> None:
    """Decode any audio ffmpeg reads (OGG, MP3...) to mono 16-bit WAV at SAMPLE_RATE.

    ffmpeg decodes to raw samples and the wave module writes the file, so the
    header is the plain 44-byte kind with no extra metadata chunks.
    """
    result = subprocess.run(
        [
            ffmpeg or ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(result.stdout)
