"""Webcam accuracy test: ``uv run --extra recognize python -m pokedex.recognizer.try_camera``.

Hold a plush, figure or card inside the square and press SPACE. A card's
printed name is read when possible; otherwise the top three picture matches
appear on the right. A toggles automatic scanning every couple of
seconds; Q quits. Each scan is saved to data/scans/ named with the top guess,
so misses can be reviewed (or later used to teach it your own toys).
"""

import argparse
import threading
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pygame
from PIL import Image

from pokedex.camera import FFmpegCamera, square_crop
from pokedex.db import PokedexDB
from pokedex.paths import DEFAULT_DATA_DIR, DataPaths
from pokedex.recognizer.clip import DEFAULT_MODEL
from pokedex.recognizer.matcher import Match
from pokedex.recognizer.scanner import load_scanner
from pokedex.ui.theme import Theme

WINDOW = (1000, 560)
PREVIEW = pygame.Rect(16, 16, 720, 405)
AUTO_INTERVAL = 2.0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--camera", default="0", help="camera index (or /dev/videoN on Linux)")
    parser.add_argument(
        "--full",
        dest="quantized",
        action="store_false",
        help="use the full-precision model instead of the quantized one the device uses",
    )
    parser.add_argument(
        "--no-cards", dest="read_cards", action="store_false", help="only match pictures"
    )
    args = parser.parse_args(argv)

    paths = DataPaths(args.data)
    with PokedexDB(paths.db) as db:
        pokemon = {p.id: p for p in db.all()}
    try:
        scanner = load_scanner(
            paths,
            ((p.id, p.name) for p in pokemon.values()),
            model=args.model,
            quantized=args.quantized,
            read_cards=args.read_cards,
        )
    except FileNotFoundError as exc:
        print(exc)
        return 1
    scans = paths.root / "scans"
    scans.mkdir(exist_ok=True)

    pygame.init()
    screen = pygame.display.set_mode(WINDOW)
    pygame.display.set_caption("Pokédex scanner test")
    theme = Theme()
    fonts = {
        "big": pygame.font.Font(theme.font_bold, 22),
        "body": pygame.font.Font(theme.font_regular, 16),
        "small": pygame.font.Font(theme.font_regular, 13),
    }
    camera = FFmpegCamera(args.camera)

    results: list[Match] = []
    status = "Hold something in the square and press SPACE"
    busy = threading.Event()
    auto = False
    last_scan = 0.0

    def scan(frame: Image.Image) -> None:
        nonlocal results, status
        started = time.perf_counter()
        crop = square_crop(frame)
        found = scanner.identify(crop)
        elapsed = (time.perf_counter() - started) * 1000
        best = pokemon[found[0].pokemon_id].name if found[0].pokemon_id in pokemon else "?"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        crop.save(scans / f"{stamp}-{best}.jpg", quality=90)
        how = "read from the card" if found[0].source == "card" else "matched by picture"
        results, status = found, f"Scanned in {elapsed:.0f} ms, {how}"
        print(f"{stamp}: " + ", ".join(
            f"{pokemon[m.pokemon_id].name} {m.confidence:.0%}" for m in found
        ))  # fmt: skip
        busy.clear()

    clock = pygame.time.Clock()
    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE)
                ):
                    return 0
                if event.type == pygame.KEYDOWN and event.key == pygame.K_a:
                    auto = not auto
            frame = camera.latest()
            keys_scan = pygame.key.get_pressed()[pygame.K_SPACE]
            due = auto and time.monotonic() - last_scan > AUTO_INTERVAL
            if frame is not None and (keys_scan or due) and not busy.is_set():
                busy.set()
                last_scan = time.monotonic()
                status = "Scanning..."
                threading.Thread(target=scan, args=(frame,), daemon=True).start()

            screen.fill(theme.bg)
            if frame is not None:
                image = pygame.image.frombytes(frame.tobytes(), frame.size, "RGB")
                screen.blit(pygame.transform.smoothscale(image, PREVIEW.size), PREVIEW)
                side = PREVIEW.height
                box = pygame.Rect(0, 0, side, side)
                box.center = PREVIEW.center
                pygame.draw.rect(screen, theme.accent, box, width=3, border_radius=8)
            else:
                error = camera.error()
                message = error or "Waiting for camera... (allow camera access if macOS asks)"
                text = fonts["body"].render(message[:90], True, theme.muted)
                screen.blit(text, text.get_rect(center=PREVIEW.center))

            _draw_results(screen, fonts, theme, results, pokemon, paths)
            help_text = f"SPACE scan    A auto-scan {'ON' if auto else 'off'}    Q quit"
            screen.blit(fonts["small"].render(help_text, True, theme.muted), (16, 440))
            screen.blit(fonts["body"].render(status, True, theme.text), (16, 470))
            pygame.display.flip()
            clock.tick(30)
    finally:
        camera.close()
        pygame.quit()


def _draw_results(screen, fonts, theme, results, pokemon, paths) -> None:
    x, y = PREVIEW.right + 20, PREVIEW.top
    screen.blit(fonts["big"].render("Top guesses", True, theme.text), (x, y))
    for rank, match in enumerate(results, 1):
        mon = pokemon.get(match.pokemon_id)
        top = y + 40 + (rank - 1) * 120
        if mon and mon.artwork_path:
            art = pygame.image.load(paths.resolve(mon.artwork_path)).convert_alpha()
            screen.blit(pygame.transform.smoothscale(art, (90, 90)), (x, top))
        name = f"{rank}. {mon.name if mon else match.pokemon_id}"
        screen.blit(fonts["body"].render(name, True, theme.text), (x + 100, top + 20))
        bar = pygame.Rect(x + 100, top + 50, 130, 10)
        pygame.draw.rect(screen, theme.panel_light, bar, border_radius=5)
        pygame.draw.rect(
            screen,
            theme.accent if rank == 1 else theme.muted,
            (bar.x, bar.y, max(10, round(bar.width * match.confidence)), bar.height),
            border_radius=5,
        )
        if match.source == "card":
            label = "Read from the card"
        else:
            label = f"{match.confidence:.0%}  (score {match.score:.3f})"
        screen.blit(fonts["small"].render(label, True, theme.muted), (x + 100, top + 64))


if __name__ == "__main__":
    raise SystemExit(main())
