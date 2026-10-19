"""Entry point and event loop: ``uv run pokedex``.

Buttons are read as keyboard keys, so GPIO buttons can be wired in with the
Pi's gpio-keys overlay (or any USB keyboard encoder) without code changes.
Touch screens work too: SDL reports taps as mouse clicks. M toggles sound.
Settings changed on the settings screen are saved to data/settings.json.
"""

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import pygame

from pokedex.db import PokedexDB
from pokedex.paths import DEFAULT_DATA_DIR, DataPaths
from pokedex.ui.assets import ImageCache
from pokedex.ui.power import Backlight, ScreenSleep, run_power_action
from pokedex.ui.render import Renderer
from pokedex.ui.scanner_service import SCAN_DONE, ScannerService, Status
from pokedex.ui.settings import Settings
from pokedex.ui.sound import EntryAudio
from pokedex.ui.state import Action, PokedexState, ScanPhase, View

KEYMAP = {
    pygame.K_UP: Action.UP,
    pygame.K_DOWN: Action.DOWN,
    pygame.K_LEFT: Action.LEFT,
    pygame.K_RIGHT: Action.RIGHT,
    pygame.K_RETURN: Action.A,
    pygame.K_SPACE: Action.A,
    pygame.K_z: Action.A,
    pygame.K_ESCAPE: Action.B,
    pygame.K_BACKSPACE: Action.B,
    pygame.K_x: Action.B,
    pygame.K_TAB: Action.SELECT,
    pygame.K_s: Action.SELECT,
    pygame.K_F1: Action.START,
    pygame.K_c: Action.START,
}
# Keys that also type letters: on the search screen they type instead of
# pressing buttons (Backspace still deletes and Enter still presses OK).
TYPING_KEYS = {pygame.K_SPACE, pygame.K_z, pygame.K_x, pygame.K_s, pygame.K_m, pygame.K_c}
PREVIEW_INTERVAL_MS = 66
"""Redraw rate on the scanner screen (about 15 fps); other screens only redraw on input."""


def _size(value: str) -> tuple[int, int]:
    width, _, height = value.lower().partition("x")
    try:
        return int(width), int(height)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {value!r}") from None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pokedex", description="Show the Pokédex screen.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="data folder")
    parser.add_argument(
        "--size",
        type=_size,
        help="window size, e.g. 800x480 (default 480x320, or the "
        "display's own size with --fullscreen)",
    )
    parser.add_argument(
        "--fullscreen", action="store_true", help="fill the screen and hide the cursor (on device)"
    )
    scanner = parser.add_argument_group("scanner")
    scanner.add_argument(
        "--camera",
        help="webcam to use, e.g. 0 or /dev/video0 (default: the Pi Camera Module if present)",
    )
    scanner.add_argument(
        "--scanner-model",
        help="CLIP model (default clip-vit-base-patch32; a Pi 5 can use clip-vit-base-patch16)",
    )
    scanner.add_argument(
        "--no-scanner", action="store_true", help="don't load the scanner (saves memory)"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = DataPaths(args.data)
    if not paths.db.exists():
        print(f"No database at {paths.db}. Run `uv run pokedex-fetch` first.", file=sys.stderr)
        return 1
    with PokedexDB(paths.db) as db:
        pokemon = db.all()
        chains = db.chains()

    # A small buffer keeps the delay between button press and cry short.
    pygame.mixer.pre_init(buffer=512)
    pygame.init()
    try:
        if args.fullscreen:
            screen = pygame.display.set_mode(args.size or (0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        else:
            screen = pygame.display.set_mode(args.size or (480, 320))
        pygame.display.set_caption("Pokédex")
        pygame.key.start_text_input()  # lets a real keyboard type into the search
        settings_file = paths.root / "settings.json"
        state = PokedexState(pokemon, chains, settings=Settings.load(settings_file))
        scanner = None
        if not args.no_scanner:
            scanner = ScannerService(
                paths,
                ((p.id, p.name) for p in pokemon),
                model=args.scanner_model,
                camera=args.camera,
            )
        run(screen, state, ImageCache(paths), EntryAudio(paths), settings_file, scanner)
    finally:
        if scanner is not None:
            scanner.stop_camera()
        pygame.quit()
    return 0


INPUT_EVENTS = {
    pygame.KEYDOWN,
    pygame.MOUSEBUTTONDOWN,
    pygame.MOUSEBUTTONUP,
    pygame.MOUSEWHEEL,
    pygame.TEXTINPUT,
}
POWER_MESSAGES = {"shutdown": "Shutting down…", "restart": "Restarting…"}


def run(
    screen: pygame.Surface,
    state: PokedexState,
    images: ImageCache,
    audio: EntryAudio,
    settings_file: Path | None = None,
    scanner: ScannerService | None = None,
    *,
    power: Callable[[str], str | None] = run_power_action,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    renderer = Renderer(screen, images)
    state.page_size = renderer.list_rows
    audio.apply(state.settings)
    sleep = ScreenSleep(clock())
    backlight = Backlight()
    while True:
        if sleep.asleep:
            screen.fill((0, 0, 0))
        else:
            update_scanner(state, scanner, renderer)
            renderer.draw(state)
        pygame.display.flip()
        before = (state.view, state.selected.id if state.selected else None)
        settings_before = state.settings

        # Sleep until something happens: no redraws while idle saves battery.
        # The scanner's live preview and the screen-sleep timer wake it early.
        timeout = wait_ms(state, sleep, clock())
        first = pygame.event.wait() if timeout is None else pygame.event.wait(timeout)
        woke = False
        for event in [first, *pygame.event.get()]:
            if is_quit(event):
                return
            if event.type in INPUT_EVENTS:
                if sleep.note_input(clock()):
                    backlight.set(True)
                    woke = True
                if woke:
                    continue  # the press that wakes the screen does nothing else
            if event.type == SCAN_DONE:
                if hasattr(event, "error"):
                    state.scan_failed(event.error)
                else:
                    state.scan_finished(event.results)
            audio.handle_event(event)
            typing = state.view is View.SEARCH
            if event.type == pygame.KEYDOWN and event.key == pygame.K_m and not typing:
                state.settings = state.settings.adjusted("sound", 1)
            handle_event(event, state, renderer)

        if state.settings != settings_before:
            audio.apply(state.settings)
            if settings_file is not None:
                state.settings.save(settings_file)
        if audio_due(before, state):
            audio.play(state.selected)
        elif state.view is not View.DETAIL and before[0] is View.DETAIL:
            audio.stop()  # leaving the entry ends its narration

        if state.power_request:
            action, state.power_request = state.power_request, None
            renderer.draw_message(POWER_MESSAGES[action], "See you soon!")
            pygame.display.flip()
            problem = power(action)
            if problem is None:
                return
            state.notice = problem

        if sleep.due(state.settings.sleep_minutes, clock()):
            sleep.asleep = True
            audio.stop()
            if scanner is not None:
                scanner.stop_camera()
            backlight.set(False)


def wait_ms(state: PokedexState, sleep: ScreenSleep, now: float) -> int | None:
    """How long the loop may block waiting for input; None means until something happens."""
    if sleep.asleep:
        return None
    waits = []
    if state.view is View.SCANNER:
        waits.append(PREVIEW_INTERVAL_MS)
    left = sleep.seconds_left(state.settings.sleep_minutes, now)
    if left is not None:
        waits.append(int(left * 1000) + 1)
    return max(1, min(waits)) if waits else None


def audio_due(before: tuple[View, int | None], state: PokedexState) -> bool:
    """Play when an entry opens or changes, not when coming back to the same one."""
    view, pokemon_id = before
    if state.view is not View.DETAIL or state.selected is None:
        return False
    return view in (View.LIST, View.SEARCH, View.SCANNER) or state.selected.id != pokemon_id


def update_scanner(state: PokedexState, scanner: ScannerService | None, renderer: Renderer) -> None:
    """Run the camera only on the scanner screen, and start scans the user asked for."""
    on_screen = state.view is View.SCANNER
    if scanner is None:
        renderer.scanner_note = "Scanner turned off (started with --no-scanner)."
        if state.scanner.phase is ScanPhase.REQUESTED:
            state.scan_failed("The scanner is turned off.")
        return
    if not on_screen:
        scanner.stop_camera()
        renderer.preview = None
        return
    scanner.start_camera()
    frame = scanner.frame(upside_down=state.settings.rotate_camera)
    if state.scanner.phase is ScanPhase.REQUESTED:
        if scanner.status is Status.LOADING:
            state.scan_failed("Still loading the scanner. Try again in a moment.")
        elif scanner.status is Status.UNAVAILABLE:
            state.scan_failed(scanner.problem)
        elif frame is None:
            state.scan_failed("The camera isn't ready yet.")
        elif scanner.scan(frame):
            state.scan_started()
            renderer.frozen = frame
    if state.scanner.phase is not ScanPhase.SCANNING:
        renderer.frozen = None
    renderer.preview = renderer.frozen or frame
    renderer.camera_problem = scanner.camera_error() if frame is None else None
    renderer.scanner_note = {
        Status.LOADING: "Loading the scanner…",
        Status.UNAVAILABLE: scanner.problem,
        Status.READY: "",
    }[scanner.status]


def is_quit(event: pygame.event.Event) -> bool:
    if event.type == pygame.QUIT:
        return True
    return (
        event.type == pygame.KEYDOWN
        and event.key == pygame.K_q
        and bool(event.mod & pygame.KMOD_CTRL)
    )


def handle_event(event: pygame.event.Event, state: PokedexState, renderer: Renderer) -> None:
    if event.type == pygame.TEXTINPUT:
        state.type_text(event.text)
    elif event.type == pygame.KEYDOWN and event.key in KEYMAP:
        if state.view is View.SEARCH and event.key in TYPING_KEYS:
            return
        state.handle(KEYMAP[event.key])
    elif event.type == pygame.MOUSEWHEEL:
        state.handle(Action.UP if event.y > 0 else Action.DOWN)
    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        handle_tap(event.pos, state, renderer)


def handle_tap(pos: tuple[int, int], state: PokedexState, renderer: Renderer) -> None:
    """Touch controls; tapping the header goes back a screen.

    Home: tap an entry to open it. Search: tap keys to type, a result to open
    it. Settings: tap a switch to flip it, the left
    or right half of the volume row to change it. List: tap a row to select
    it, tap it again to open it; tap the type filter to cycle it. Detail: tap
    the left or right edge for previous/next, the middle for the evolution
    chain. Evolution: tap a Pokémon to select it, tap it again to open it.
    Scanner: tap the camera view to scan, a guess to open it.
    """
    if state.view is View.LIST and renderer.filter_hit.collidepoint(pos):
        state.handle(Action.SELECT)
    elif state.view is View.SEARCH and renderer.header.collidepoint(pos):
        state.view = View.HOME  # B would only delete a letter
    elif renderer.header.collidepoint(pos):
        state.handle(Action.B)
    elif state.view is View.SCANNER:
        for rect, index in renderer.choice_hits:
            if rect.collidepoint(pos):
                state.choose_scan_result(index)
                return
        if renderer.preview_hit.collidepoint(pos) and state.scanner.phase is ScanPhase.LIVE:
            state.handle(Action.A)
    elif state.view is View.SEARCH:
        for rect, (row, index) in renderer.key_hits:
            if rect.collidepoint(pos):
                state.search.in_results = False
                state.search.press(row, index)
                return
        for rect, index in renderer.result_hits:
            if rect.collidepoint(pos):
                state.search.result_index = index
                state.open_species(state.search.results[index].id, return_to=View.SEARCH)
                return
    elif state.view is View.HOME:
        for rect, index in renderer.menu_hits:
            if rect.collidepoint(pos):
                state.open_menu(index)
                return
    elif state.view is View.SETTINGS:
        for rect, row in renderer.settings_hits:
            if rect.collidepoint(pos):
                delta = -1 if pos[0] < rect.centerx else 1
                state.change_setting(row, delta)
                return
    elif state.view is View.LIST:
        for rect, index in renderer.row_hits:
            if rect.collidepoint(pos):
                if index == state.index:
                    state.handle(Action.A)
                else:
                    state.select_index(index)
                return
    elif state.view is View.DETAIL:
        edge = renderer.w // 5
        if pos[0] < edge:
            state.handle(Action.LEFT)
        elif pos[0] > renderer.w - edge:
            state.handle(Action.RIGHT)
        else:
            state.handle(Action.A)
    elif state.view is View.EVOLUTION:
        for rect, (stage, row) in renderer.evo_hits:
            if rect.collidepoint(pos):
                if (stage, row) == (state.evo_stage, state.evo_row):
                    state.handle(Action.A)
                else:
                    state.move_evo_cursor(stage, row)
                return
