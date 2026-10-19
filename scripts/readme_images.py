"""Render the README's screenshots and animated tour from the real UI.

    uv run python scripts/readme_images.py

Needs a fetched database (data/pokedex.db). Writes PNGs and a GIF to
docs/images/. Screens are drawn at 2x the device's 480x320 so they stay
sharp on high-density displays.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pathlib import Path  # noqa: E402

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from pokedex import DataPaths, PokedexDB  # noqa: E402
from pokedex.ui.assets import ImageCache  # noqa: E402
from pokedex.ui.render import Renderer  # noqa: E402
from pokedex.ui.settings import Settings  # noqa: E402
from pokedex.ui.state import MENU, Action, PokedexState, View  # noqa: E402

OUT = Path(__file__).parents[1] / "docs" / "images"
SIZE = (960, 640)


def main() -> None:
    paths = DataPaths()
    with PokedexDB(paths.db) as db:
        pokemon, chains = db.all(), db.chains()
    OUT.mkdir(parents=True, exist_ok=True)

    pygame.init()
    screen = pygame.display.set_mode(SIZE)
    renderer = Renderer(screen, ImageCache(paths))
    state = PokedexState(pokemon, chains, page_size=renderer.list_rows, settings=Settings())

    def frame() -> Image.Image:
        renderer.draw(state)
        return Image.frombytes("RGB", SIZE, pygame.image.tobytes(screen, "RGB"))

    def save(name: str) -> None:
        frame().save(OUT / f"{name}.png", optimize=True)

    # Stills
    save("home")
    state.open_menu(0)
    state.select_index(5)  # Charizard
    save("list")
    state.handle(Action.A)
    save("detail")
    state.open_species(133)  # Eevee
    state.handle(Action.A)
    save("evolution")
    state.open_species(1)
    state.handle(Action.A)
    save("evolution-line")
    state.view = View.HOME
    state.open_menu(next(i for i, (_, v) in enumerate(MENU) if v is View.SETTINGS))
    save("settings")
    state.open_menu(next(i for i, (_, v) in enumerate(MENU) if v is View.SEARCH))
    state.type_text("char")
    state.search.key_row, state.search.key_index = 1, 5  # cursor on "P", as if typing
    save("search")

    # Animated tour: home -> list -> Pikachu -> its evolutions -> Raichu.
    tour = PokedexState(pokemon, chains, page_size=renderer.list_rows)
    state = tour
    steps: list[tuple[Action | None, int]] = [
        (None, 1400),
        (Action.A, 900),
        *[(Action.DOWN, 160)] * 24,
        (None, 700),
        (Action.A, 2000),
        (Action.RIGHT, 1400),
        (Action.LEFT, 1400),
        (Action.A, 2000),
        (Action.RIGHT, 900),
        (Action.A, 2000),
        (Action.B, 900),
        (Action.B, 900),
        (Action.SELECT, 1200),
        (Action.SELECT, 1200),
        (Action.SELECT, 1400),
    ]
    frames, durations = [], []
    for action, duration in steps:
        if action is not None:
            state.handle(action)
        frames.append(frame().resize((480, 320), Image.Resampling.LANCZOS))
        durations.append(duration)
    frames[0].save(
        OUT / "tour.gif",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    pygame.quit()
    print(f"Wrote {len(list(OUT.iterdir()))} images to {OUT}")


if __name__ == "__main__":
    main()
