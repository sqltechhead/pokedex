import io
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

import pokedex.camera as camera  # noqa: E402
from pokedex.models import BaseStats, Pokemon  # noqa: E402
from pokedex.paths import DataPaths  # noqa: E402
from pokedex.ui.app import KEYMAP, audio_due, handle_tap, update_scanner  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.render import Renderer  # noqa: E402
from pokedex.ui.scanner_service import Status  # noqa: E402
from pokedex.ui.state import (  # noqa: E402
    Action,
    PokedexState,
    ScanPhase,
    ScanResult,
    View,
)

STATS = BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1)


@pytest.fixture
def state() -> PokedexState:
    mons = [
        Pokemon(id=i, name=f"Mon{i}", type1="normal", height_dm=1, weight_hg=1, stats=STATS)
        for i in (1, 2, 25)
    ]
    return PokedexState(mons)


class TestScannerState:
    def test_start_opens_scanner_from_anywhere(self, state):
        state.handle(Action.A)  # into the list
        state.handle(Action.START)
        assert state.view is View.SCANNER
        assert state.scanner.phase is ScanPhase.LIVE
        assert KEYMAP[pygame.K_F1] is Action.START

    def test_a_requests_a_scan_and_b_cancels(self, state):
        state.open_scanner()
        state.handle(Action.A)
        assert state.scanner.phase is ScanPhase.REQUESTED
        state.scan_started()
        state.handle(Action.B)
        assert state.scanner.phase is ScanPhase.LIVE
        state.scan_finished([ScanResult(25, 0.9)])  # arrives after cancelling: ignored
        assert state.view is View.SCANNER

    def test_card_or_confident_match_opens_the_entry(self, state):
        for result in (ScanResult(25, 0.1, from_card=True), ScanResult(25, 0.8)):
            state.open_scanner()
            state.handle(Action.A)
            state.scan_started()
            state.scan_finished([result])
            assert state.view is View.DETAIL
            assert state.selected.id == 25
            state.handle(Action.B)
            assert state.view is View.SCANNER

    def test_unsure_match_offers_choices(self, state):
        state.open_scanner()
        state.handle(Action.A)
        state.scan_started()
        state.scan_finished([ScanResult(1, 0.3), ScanResult(999, 0.2), ScanResult(2, 0.1)])
        assert state.scanner.phase is ScanPhase.CHOOSE
        assert [c.pokemon_id for c in state.scanner.choices] == [1, 2]  # 999 isn't fetched
        state.handle(Action.DOWN)
        state.handle(Action.A)
        assert state.selected.id == 2

    def test_nothing_recognised_shows_a_message(self, state):
        state.open_scanner()
        state.handle(Action.A)
        state.scan_started()
        state.scan_finished([ScanResult(999, 0.9)])
        assert state.scanner.phase is ScanPhase.LIVE
        assert "Try again" in state.scanner.message

    def test_entry_from_scanner_cries(self, state):
        state.open_scanner()
        before = (state.view, state.selected.id)
        state.handle(Action.A)
        state.scan_started()
        state.scan_finished([ScanResult(1, 0.9)])
        assert audio_due(before, state)


def test_mjpeg_frames_splits_a_stream():
    jpegs = b""
    for color in ("red", "blue"):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 6), color).save(buffer, "JPEG")
        jpegs += buffer.getvalue()
    frames = list(camera.mjpeg_frames(io.BytesIO(b"junk" + jpegs), chunk_size=50))
    assert [f.size for f in frames] == [(8, 6), (8, 6)]
    assert frames[0].getpixel((4, 3))[0] > 200  # red
    assert frames[1].getpixel((4, 3))[2] > 200  # blue


def test_open_camera_prefers_the_pi_camera(monkeypatch):
    made = []
    monkeypatch.setattr(camera, "RpicamCamera", lambda: made.append(("pi", None)) or "pi")
    monkeypatch.setattr(
        camera, "FFmpegCamera", lambda device: made.append(("webcam", device)) or "webcam"
    )
    monkeypatch.setattr(camera.shutil, "which", lambda name: "/usr/bin/rpicam-vid")
    assert camera.open_camera() == "pi"
    assert camera.open_camera("1") == "webcam"  # a named device means a webcam
    monkeypatch.setattr(camera.shutil, "which", lambda name: None)
    assert camera.open_camera() == "webcam"
    assert made == [("pi", None), ("webcam", "1"), ("webcam", "0")]


class FakeService:
    def __init__(self, status=Status.READY, frame=None):
        self.status, self.problem = status, "Scanner not installed."
        self._frame, self.camera_running, self.scanned = frame, False, []

    def start_camera(self):
        self.camera_running = True

    def stop_camera(self):
        self.camera_running = False

    def frame(self, *, upside_down=False):
        return self._frame if self.camera_running else None

    def camera_error(self):
        return None

    def scan(self, frame):
        self.scanned.append(frame)
        return True


@pytest.fixture
def renderer(tmp_path):
    pygame.init()
    yield Renderer(pygame.display.set_mode((480, 320)), ImageCache(DataPaths(tmp_path)))
    pygame.quit()


class TestAppScanner:
    def test_camera_runs_only_on_the_scanner_screen(self, state, renderer):
        service = FakeService(frame=Image.new("RGB", (640, 480)))
        update_scanner(state, service, renderer)
        assert not service.camera_running
        state.open_scanner()
        update_scanner(state, service, renderer)
        assert service.camera_running
        assert renderer.preview is not None
        state.handle(Action.B)
        update_scanner(state, service, renderer)
        assert not service.camera_running

    def test_requested_scan_starts_and_freezes_the_frame(self, state, renderer):
        frame = Image.new("RGB", (640, 480))
        service = FakeService(frame=frame)
        state.open_scanner()
        update_scanner(state, service, renderer)
        state.handle(Action.A)
        update_scanner(state, service, renderer)
        assert service.scanned == [frame]
        assert state.scanner.phase is ScanPhase.SCANNING
        assert renderer.preview is frame

    @pytest.mark.parametrize(
        ("status", "frame", "message"),
        [
            (Status.LOADING, Image.new("RGB", (4, 4)), "Still loading"),
            (Status.UNAVAILABLE, Image.new("RGB", (4, 4)), "not installed"),
            (Status.READY, None, "isn't ready"),
        ],
    )
    def test_scan_problems_are_explained(self, state, renderer, status, frame, message):
        service = FakeService(status=status, frame=frame)
        state.open_scanner()
        update_scanner(state, service, renderer)
        state.handle(Action.A)
        update_scanner(state, service, renderer)
        assert state.scanner.phase is ScanPhase.LIVE
        assert message in state.scanner.message

    def test_without_a_scanner_service(self, state, renderer):
        state.open_scanner()
        state.handle(Action.A)
        update_scanner(state, None, renderer)
        assert "turned off" in state.scanner.message

    def test_tap_preview_scans_and_tap_choice_opens(self, state, renderer):
        state.open_scanner()
        renderer.draw(state)
        handle_tap(renderer.preview_hit.center, state, renderer)
        assert state.scanner.phase is ScanPhase.REQUESTED
        state.scan_started()
        state.scan_finished([ScanResult(1, 0.3), ScanResult(25, 0.2)])
        renderer.draw(state)
        second = next(rect for rect, index in renderer.choice_hits if index == 1)
        handle_tap(second.center, state, renderer)
        assert state.view is View.DETAIL
        assert state.selected.id == 25


@pytest.mark.parametrize("size", [(480, 320), (800, 480), (320, 240)])
def test_renders_every_scanner_phase(tmp_path, state, size):
    pygame.init()
    try:
        screen = pygame.display.set_mode(size)
        renderer = Renderer(screen, ImageCache(DataPaths(tmp_path)))
        state.open_scanner()
        for preview in (None, Image.new("RGB", (640, 480), "green")):
            renderer.preview = preview
            renderer.draw(state)
        renderer.camera_problem = "No camera found"
        renderer.preview = None
        renderer.draw(state)
        state.scanner.message = "Couldn't recognise that. Try again."
        renderer.scanner_note = "Loading the scanner…"
        renderer.draw(state)
        state.scan_started()
        renderer.draw(state)
        state.scan_finished([ScanResult(1, 0.3), ScanResult(2, 0.2), ScanResult(25, 0.1)])
        renderer.draw(state)
        assert len(renderer.choice_hits) == 3
        for rect, _ in renderer.choice_hits:
            assert screen.get_rect().contains(rect)
    finally:
        pygame.quit()


def test_service_loads_and_scans_in_the_background(monkeypatch, tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("onnxruntime")
    import pokedex.recognizer.scanner as scanner_module
    from pokedex.recognizer.matcher import Match
    from pokedex.ui.scanner_service import SCAN_DONE, ScannerService

    class FakeScanner:
        def identify(self, image, top=3):
            assert image.size == (480, 480)  # the centre square of the frame
            return [Match(25, 1.0, 1.0, source="card")]

    monkeypatch.setattr(scanner_module, "load_scanner", lambda *a, **k: FakeScanner())
    pygame.init()
    try:
        pygame.display.set_mode((10, 10))
        service = ScannerService(DataPaths(tmp_path), [(25, "Pikachu")])
        for _ in range(100):
            if service.status is not Status.LOADING:
                break
            time.sleep(0.02)
        assert service.status is Status.READY
        assert service.scan(Image.new("RGB", (640, 480)))
        done = None
        for _ in range(100):
            done = next((e for e in pygame.event.get() if e.type == SCAN_DONE), None)
            if done:
                break
            time.sleep(0.02)
        assert done is not None
        assert done.results == [ScanResult(25, 1.0, from_card=True)]
    finally:
        pygame.quit()
