# CLAUDE.md

A real, offline Pokédex for a 3D-printed handheld. This file is context for
Claude Code sessions: what the project is, decisions already made and why,
gotchas, and where things stand. The README covers usage.

## The device

- **Target: Raspberry Pi Pico 2** (RP2350, 520 KB RAM, no OS) running
  **CircuitPython**. Switched from the Pi Zero 2 W on 2026-10-21; the Zero
  version (pygame UI, camera scanner) is in git history before that.
- **No scanner/camera**: the Pico can't run recognition. Dropped deliberately.
- **Docs follow the plan:** `docs/hardware.md` mirrors its hardware
  sections; README and this file must agree with it. When code changes
  something the plan describes (buttons, card layout, pins), update the
  plan's page *and* its `plan.md` too (Artifact tool, publish with `url`).
- **Hardware source of truth: the "Pokédex Handheld Plan" artifact**
  (https://claude.ai/artifact/UjDWTx9Sn6SvYG6ow1UfMZ; read it and its files
  with the Artifact tool). Parts were bought 2026-11-03 for two builds (for
  Marshall, a child: keep it safe and simple).
- Screen: **Waveshare 3.5" (G), ST7796S, 480×320, 16-bit SPI**, via the plan's
  `firmware/st7796s.py`. XPT2046 touch shares the bus; TP_CS (GP26) is held
  high and touch is unused until calibrated on the real screen.
- 10 buttons via `keypad.Keys` in `pins.BUTTON_NAMES` order: D-pad, A, B,
  START (menu from anywhere), SELECT (replay entry / search results / region
  filter in the list), L/R (type filter in the list, ±10 on an entry). On an
  entry ▲▼ = prev/next and ◀▶ = tabs (INFO, TYPES, ABILITIES, MOVES); on
  MOVES ▲▼ scroll instead.
- Features: list with type + region filters, entry tabs, evolution map,
  search, "Who's that Pokémon?" quiz (`dex.quiz`, silhouettes `sil/`, score
  kept for the session), shiny mode (off by default; `shiny/<folder>/`, falls back to normal),
  the Pokédex always opens at #001 with filters cleared (Browse's Show keeps picks),
  brightness (backlight 10-100%), start-up splash + original jingle, and
  **Browse** (`dex.browse`): 17 categories built on the PC
  (`sdcard/categories.py` → `cat/categories.tsv`, `cat/<slug>.tsv` labels and
  totals, `cat/<slug>.bin` = per Pokémon in index order a count byte + u16 LE
  value numbers, `cat/has.bin` = per category a bit per Pokémon). Picks OR
  within a category, AND across categories, and AND with the type/region
  filters. Faceted: counts are among Pokémon matching the *other* categories'
  picks; zero-count values and empty categories are hidden (picked ones stay);
  cursors index the shown lists. B in the list clears all filters incl. picks.
- Audio: MAX98357A over I2S, two speakers in parallel; WAV through `audiomixer`.
- Battery: divider on GP28, read every 30 s, icon top-right of every header
  (yellow below 3.45 V). Header text ends at `HEADER_RIGHT` to leave room.
- microSD on its own SPI bus, mounted at `/sd`; settings saved there.
- **Pins: `firmware/pins.py`**, plus `st7796s.py` and `hw_test.py`, copied
  verbatim from the plan (only numeric underscores removed and `AUDIO_RATE`
  set to 22050). Ruff excludes them. Keep them in sync with the plan.
- **Everything heavy runs on the PC**; the Pico only reads the card.

## Layout and commands

- `src/pokedex/` (PC, CPython via uv): `models.py`, `db.py` (SQLite,
  `MIGRATIONS` dict), `paths.py`, `fetcher/` → `pokedex-fetch`, `narrator/` →
  `pokedex-narrate`, `sdcard/` → `pokedex-sdcard` (builds `build/sd/pokedex/`:
  `index.tsv` (6th column = generation), `mon/NNNN.json` (incl. `region`,
  `abilities`, `moves`, `moves_from`, `matchups`),
  `art|spr|ev72|ev44|ev26|sil/NNNN.bmp`, `shiny/<same>/`, `cry|say/NNNN.wav`,
  `sfx/startup|correct|wrong.wav` (synthesised in `sdcard/sounds.py`),
  `fonts/*.bdf`).
- **Fetched data:** `pokedex-fetch` also stores generation, abilities,
  level-up moves (newest *main* game via `MOVE_VERSIONS`: PokéAPI's version
  group ids are NOT release order, e.g. blue-japan is 29), shiny artwork, and
  tables `move`, `ability`, `type_effect`. Old rows are filled in by the
  details pass (`generation IS NULL`) and the species pass (colour, shape,
  habitat, legendary/mythical/baby, egg groups; `color IS NULL`). Level 0 =
  learned on evolution. Starters are a hand-written list in `categories.py`.
- `firmware/` (copied to CIRCUITPY): `code.py` → `lib/dex/app.py`. Pure,
  PC-tested modules: `state`, `index`, `records`, `search`, `keyboard`,
  `evolution`, `settings`, `units`, `timing`, `battery`, `quiz`, `browse`, `theme`. Hardware-only:
  `hardware`, `screens`, `audio`, `app` (untestable on the PC).
- **Simulator:** `uv run --group sim python sim/pokedex_sim.py` runs the real
  firmware on Blinka displayio in a pygame window (keyboard = buttons, swaps
  in fake `dex.hardware`/`dex.audio` via sys.modules, `build/sd` = card).
  `--shots DIR` runs `TOUR` and saves PNGs; use it to check screen changes.
  blinka-displayio-pygamedisplay 4.1.0 imports an unpublished
  `keypad_pygame`, hence the stub `sim/keypad_pygame.py`.
- Tests: `uv run --all-extras pytest` (pytest `pythonpath` adds
  `firmware/lib`). Lint: `uv run ruff check . && uv run ruff format .`.
- `data/` (~1.6 GB incl. old models) and `build/` are git-ignored.

## Decisions and gotchas

- **Firmware Python subset:** no `match`, dataclasses, enum, typing,
  annotations, walrus, `str.isalnum/capitalize/title`, numeric underscores,
  `zip(strict=)`. `tests/firmware/test_fw_compat.py` enforces most of it;
  ruff ignores B905 under `firmware/**`. f-strings are fine.
- **Floats are single precision on the Pico**: units use integer maths.
- **Search keys are made on the PC** (`sdcard/entries.search_key`, NFKD)
  because CircuitPython has no unicodedata.
- **Index in RAM** stores types as a bytearray of codes (`dex.index`), list
  state works on index positions, entries are read from SD on demand.
- **Fonts:** BDFs generated from DejaVu with Pillow (`sdcard/fonts.py`);
  charset = all data text + every char in `firmware/**/*.py`, so new UI
  symbols are covered after re-running `pokedex-sdcard`. Space glyph is 1×1.
- **BMPs:** 8-bit palette, index 0 transparent; soft edges pre-blended onto
  `theme.PANEL`. Pillow's `point()` on a P image maps the palette, not the
  indices: use `Image.frombytes("L", ...)` to get indices.
- **WAVs:** ffmpeg decodes to raw s16le, stdlib `wave` writes a plain 44-byte
  header (no LIST chunk). 22050 Hz mono; must match `dex.audio.SAMPLE_RATE`.
- Narration: Piper `en_US-ryan-high` (non-commercial) with a device effect;
  "Pokémon" respelled in `narrator/script.py` `PRONUNCIATIONS`. Don't imitate
  real voice actors. Dev Mac is Intel macOS 12: onnxruntime pinned `<1.20`.
- **Labels use `background_tight=True`**: bitmap_label's default box is the
  font's full ascent (É, ♀), which draws plain text ~6 px low. Found in the
  simulator. Hidden vectorio shapes go to x = -1000 (`OFFSCREEN`), not -100,
  or wide ones poke back on screen.
- Cry plays then narration starts from `EntryAudio.poll()`; START on an entry
  replays. Screens only resend changed areas (`set_text`/`set_color` guards).

## Status (2026-11-03)

- Done: Pico rewrite (firmware + `pokedex-sdcard`), firmware aligned to the
  plan's parts and pins (ST7796S, 10 buttons, battery icon); then brightness,
  shiny mode, start-up jingle, quiz, type matchups, abilities, moves and the
  region filter, then Browse by category (17 categories). 169 tests passing; full fetch done (no failures); real card
  built from all 1,025 (~570 MB).
- Simulator tour verified every screen, incl. the splash, quiz (question and
  answer), all four entry tabs, the region filter, shiny mode and Browse
  (Legendary → colour counts among legendaries; Baby hides Top 20). The tour's menu counts depend on MENU
  order: adding a home entry shifts them.
- **Never run on a Pico yet.** Unverified: ST7796S init/MADCTL/inversion, SPI
  speeds, RAM headroom, WAV streaming from SD, font load speed,
  CircuitPython-on-RP2350 module availability. First step: `import hw_test`.
- Plan artifact updated 2026-11-03 (version 7): sections 1, 6, 7, 8 and 13
  now describe the code as built (buttons, card layout, `pokedex-sdcard`),
  and its `pins.py` matches the repo's.
- No README screenshots (the old pygame ones were removed).
- GitHub `sqltechhead/pokedex`, branch `main`; stray `master` branch still
  to delete once the default branch is `main`.
- Next ideas: caught tracking, touch, cry quiz, favourites/team, themes.
