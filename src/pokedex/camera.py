"""Reading frames from a camera.

Two sources, both run as a subprocess that a background thread reads from:

- RpicamCamera: the Raspberry Pi Camera Module, through the rpicam-vid
  command that ships with Raspberry Pi OS. This sidesteps picamera2, which
  only installs into the system Python, not the one uv manages.
- FFmpegCamera: a webcam (the Mac's FaceTime camera, or a USB camera),
  through ffmpeg: the system one, or the copy bundled by imageio-ffmpeg.

open_camera() picks whichever is available.
"""

import io
import shutil
import subprocess
import sys
import threading
from typing import Protocol

from PIL import Image

FRAME_SIZE = (640, 480)


class Camera(Protocol):
    def latest(self) -> Image.Image | None: ...

    def error(self) -> str | None: ...

    def close(self) -> None: ...


class _SubprocessCamera:
    """Runs a capture command and keeps the newest frame it produces."""

    def __init__(self, command: list[str]) -> None:
        self._process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
        )
        self._frame: Image.Image | None = None
        self._lock = threading.Lock()
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self) -> None:
        assert self._process.stdout is not None
        for frame in self._frames(self._process.stdout):
            with self._lock:
                self._frame = frame

    def _frames(self, stream: io.RawIOBase):  # pragma: no cover - overridden
        raise NotImplementedError

    def latest(self) -> Image.Image | None:
        with self._lock:
            return self._frame

    def error(self) -> str | None:
        """The command's error message if it has exited (e.g. no camera or no permission)."""
        if self._process.poll() is None:
            return None
        assert self._process.stderr is not None
        return self._process.stderr.read().decode(errors="replace").strip() or "camera stopped"

    def close(self) -> None:
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()


def webcam_input(device: str) -> list[str]:
    if sys.platform == "darwin":
        return ["-f", "avfoundation", "-framerate", "30", "-video_size", "1280x720", "-i", device]
    path = device if device.startswith("/dev/") else f"/dev/video{device}"
    return ["-f", "v4l2", "-i", path]


def ffmpeg_exe() -> str | None:
    if found := shutil.which("ffmpeg"):
        return found
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    return imageio_ffmpeg.get_ffmpeg_exe()


class FFmpegCamera(_SubprocessCamera):
    """A webcam read through ffmpeg as raw RGB frames."""

    def __init__(
        self,
        device: str = "0",
        size: tuple[int, int] = (640, 360),
        *,
        input_args: list[str] | None = None,
    ) -> None:
        """input_args replaces the webcam with any ffmpeg input (used by the tests)."""
        exe = ffmpeg_exe()
        if exe is None:
            raise FileNotFoundError("ffmpeg not found: install it or `uv sync` the dev group")
        self.size = size
        width, height = size
        super().__init__([
            exe, "-hide_banner", "-loglevel", "error",
            *(input_args or webcam_input(device)),
            "-vf", f"scale={width}:{height}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ])  # fmt: skip

    def _frames(self, stream):
        frame_bytes = self.size[0] * self.size[1] * 3
        buffer = b""
        while chunk := stream.read(frame_bytes - len(buffer)):
            buffer += chunk
            if len(buffer) == frame_bytes:
                yield Image.frombytes("RGB", self.size, buffer)
                buffer = b""


class RpicamCamera(_SubprocessCamera):
    """The Raspberry Pi Camera Module, streamed by rpicam-vid as MJPEG."""

    def __init__(self, size: tuple[int, int] = FRAME_SIZE, *, fps: int = 15) -> None:
        width, height = size
        command = [
            "rpicam-vid", "--nopreview", "--timeout", "0",
            "--width", str(width), "--height", str(height), "--framerate", str(fps),
            "--codec", "mjpeg", "--output", "-",
        ]  # fmt: skip
        super().__init__(command)

    def _frames(self, stream):
        yield from mjpeg_frames(stream)


def mjpeg_frames(stream, chunk_size: int = 65536):
    """Split a stream of back-to-back JPEGs into images."""
    buffer = b""
    while chunk := stream.read(chunk_size):
        buffer += chunk
        while True:
            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9", start + 2)
            if start < 0 or end < 0:
                break
            jpeg, buffer = buffer[start : end + 2], buffer[end + 2 :]
            try:
                image = Image.open(io.BytesIO(jpeg))
                image.load()
            except OSError:
                continue  # a damaged frame: skip it
            yield image.convert("RGB")


def square_crop(frame: Image.Image) -> Image.Image:
    """The centre square the scanner looks at (the guide drawn on screen)."""
    side = min(frame.size)
    left, top = (frame.width - side) // 2, (frame.height - side) // 2
    return frame.crop((left, top, left + side, top + side))


def open_camera(device: str | None = None) -> Camera:
    """The Pi Camera Module when rpicam-vid exists (and no device is named), else a webcam."""
    if device is None and shutil.which("rpicam-vid"):
        return RpicamCamera()
    return FFmpegCamera(device or "0")
