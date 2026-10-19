"""Runs the camera and recognition off the UI thread.

The recognition models load in the background as soon as the app starts, so
the first scan doesn't wait for them. The camera only runs while the scanner
screen is open. Finished scans arrive as SCAN_DONE events, so the event loop
wakes up for them like for a button press.
"""

import threading
from collections.abc import Iterable
from enum import Enum, auto

import pygame

from pokedex.paths import DataPaths
from pokedex.ui.state import ScanResult

SCAN_DONE = pygame.event.custom_type()
"""Carries results: list[ScanResult], or error: str."""
MODELS_LOADED = pygame.event.custom_type()


class Status(Enum):
    LOADING = auto()
    READY = auto()
    UNAVAILABLE = auto()


class ScannerService:
    def __init__(
        self,
        paths: DataPaths,
        names: Iterable[tuple[int, str]],
        *,
        model: str | None = None,
        camera: str | None = None,
    ) -> None:
        self._paths = paths
        self._names = list(names)
        self._model = model
        self._camera_device = camera
        self._scanner = None
        self._camera = None
        self._busy = threading.Lock()
        self.status = Status.LOADING
        self.problem = ""
        """Why scanning is unavailable, in words for the screen."""
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        try:
            from pokedex.recognizer.clip import DEFAULT_MODEL
            from pokedex.recognizer.scanner import load_scanner
        except ImportError:
            self._unavailable("Scanner not installed. Run: uv sync --extra recognize")
            return
        try:
            self._scanner = load_scanner(
                self._paths, self._names, model=self._model or DEFAULT_MODEL
            )
        except FileNotFoundError:
            self._unavailable("No scanner data. Run: uv run --extra recognize pokedex-embed")
            return
        except Exception as exc:  # a broken model file shouldn't take the Pokédex down
            self._unavailable(f"Scanner failed to load: {exc}")
            return
        self.status = Status.READY
        pygame.event.post(pygame.event.Event(MODELS_LOADED))

    def _unavailable(self, problem: str) -> None:
        self.status, self.problem = Status.UNAVAILABLE, problem
        pygame.event.post(pygame.event.Event(MODELS_LOADED))

    # Camera

    def start_camera(self) -> None:
        if self._camera is None:
            from pokedex.camera import open_camera

            try:
                self._camera = open_camera(self._camera_device)
            except FileNotFoundError as exc:
                self.problem = str(exc)

    def stop_camera(self) -> None:
        if self._camera is not None:
            self._camera.close()
            self._camera = None

    @property
    def camera_running(self) -> bool:
        return self._camera is not None

    def frame(self, *, upside_down: bool = False):
        """The newest camera frame (a PIL image), or None while it starts.

        upside_down turns it the right way up, for a camera mounted inverted
        in the shell; doing it here works for every camera and takes effect at once.
        """
        frame = self._camera.latest() if self._camera is not None else None
        if frame is not None and upside_down:
            from PIL import Image

            frame = frame.transpose(Image.Transpose.ROTATE_180)
        return frame

    def camera_error(self) -> str | None:
        if self._camera is None:
            return self.problem or None
        return self._camera.error()

    # Scanning

    def scan(self, frame) -> bool:
        """Start recognising a frame; False if not ready or a scan is running."""
        if self.status is not Status.READY or not self._busy.acquire(blocking=False):
            return False
        threading.Thread(target=self._scan, args=(frame,), daemon=True).start()
        return True

    def _scan(self, frame) -> None:
        from pokedex.camera import square_crop

        try:
            matches = self._scanner.identify(square_crop(frame))
            results = [
                ScanResult(m.pokemon_id, m.confidence, from_card=m.source == "card")
                for m in matches
            ]
            event = pygame.event.Event(SCAN_DONE, results=results)
        except Exception as exc:
            event = pygame.event.Event(SCAN_DONE, error=f"Scan failed: {exc}")
        finally:
            self._busy.release()
        pygame.event.post(event)
