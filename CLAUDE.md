# CLAUDE.md

A real, offline Pokédex for a 3D-printed handheld. This file is context for
Claude Code sessions: what the project is, decisions already made and why,
gotchas, and where things stand. The README covers usage.

## The device

- **Target: Raspberry Pi Zero 2 W** (512 MB RAM, slim shell, cheap). The user
  decided to wait for Zero stock rather than test on a Pi 5 first; the code
  still runs on a Pi 5 (same camera connector), which the README notes.
- Screen designed at **480×320**, scales to any size.
- Buttons are read as **keyboard keys** (GPIO via the `gpio-key` overlay):
  D-pad, A (Enter/Space/Z), B (Esc/Backspace/X), SELECT (Tab/S),
  START (F1/C, keycode 59). Touch works too.
- Camera Module 3 on a 22-pin Pi 5/Zero cable. No audio jack on either
  board: I2S amp (e.g. MAX98357A) or USB audio.
- Parts list, GPIO pin plan and config.txt: `docs/hardware.md` (planned, not yet
  built). The Zero has no DSI port, so the screen is a 480×320 SPI LCD.
- **Everything heavy runs on the PC** (fetch, narration, recognition
  references); the device only reads files. Must work fully offline.

## Layout and commands

- `src/pokedex/`: `models.py` (Pydantic `Pokemon`, `EvolutionChain`),
  `db.py` (SQLite via plain `sqlite3`, explicit schema + `MIGRATIONS` dict),
  `paths.py` (`DataPaths`), `search.py`, `units.py`, `camera.py`.
- `fetcher/` → `pokedex-fetch`; `narrator/` → `pokedex-narrate`;
  `recognizer/` → `pokedex-embed` and the scanner; `ui/` → `pokedex`.
- `ui/state.py` is **pure navigation state (no pygame)**; `render.py` draws;
  `app.py` is the event loop. Keep that split: state is unit-tested headless.
- Optional extras: `narrate` (Piper, numpy, scipy, soundfile) and
  `recognize` (onnxruntime, numpy, scipy, pillow, tokenizers). Use
  `uv run --all-extras ...` in development so extras aren't dropped.
- Tests: `uv run --all-extras pytest` (offline, SDL dummy drivers).
  Lint: `uv run ruff check . && uv run ruff format .` (Markdown excluded).
- `data/` (~1.6 GB) is git-ignored; README "Get the data" rebuilds it.
- `scripts/readme_images.py` regenerates `docs/images/`;
  `scripts/demo_video.py` records `docs/media/pokedex-demo.mp4` with sound.

## Decisions and gotchas

- **Dev Mac is Intel, macOS 12.** onnxruntime is pinned `<1.20` for
  darwin/x86_64 only (newer wheels need macOS 13 / arm64). PyTorch and
  OpenCV have no usable builds there, so neither is used: CLIP and OCR run
  on ONNX Runtime with numpy/scipy/Pillow; webcams are read through ffmpeg
  (`imageio-ffmpeg` dev dependency).
- **Pi camera via `rpicam-vid` subprocess (MJPEG), not picamera2**, because
  picamera2 only installs into the system Python, not uv's.
- **Scanner:** card names first (PaddleOCR v3 English det/rec ONNX models,
  own pre/post-processing, fuzzy name match preferring tall text), then
  CLIP picture matching (blend 40% text prompts / 60% artwork). Default
  model `clip-vit-base-patch32` **quantized** for the Zero; `patch16` is
  more accurate (Pi 5 only). Plush confidences across 1,025 Pokémon are low
  (5-25%), so plushies usually get the "Is it…?" top-3 chooser; cards open
  directly. Auto-open threshold = Settings → Scanner sensitivity.
- **Audio:** cry then narration on one reserved mixer channel; narration is
  started from the channel's end event, never `Channel.queue` (stopping a
  channel triggers its queue, which caused overlapping audio).
- **Narration:** Piper `en_US-ryan-high` (non-commercial licence) with a
  light "device" effect. "Pokémon" is respelled "Pokemon" and "Poké" as
  "Pokeh" in `narrator/script.py` `PRONUNCIATIONS` (espeak otherwise says
  "PAH-kay-mun"). Don't imitate real voice actors (e.g. Dexter's).
- Cries from PokéAPI are named `.ogg` but some are MP3 inside; pygame and
  ffmpeg detect by content, so leave them.
- The event loop only redraws on input (battery); the scanner screen
  redraws at ~15 fps and screen sleep adds a timeout. Shut down/restart
  refuse to run off a Raspberry Pi (`ui/power.py`).

## Status (2026-10-19)

- Done: fetch of all 1,025 Pokémon (cries, evolution chains, narration,
  scanner references), UI (home, list, entry, evolution, search with
  on-screen keyboard, scanner, settings incl. units, screen sleep, safe
  shut down), README, tests (162 passing).
- GitHub: `sqltechhead/pokedex`, branch `main`. A stray `master` branch
  (GitHub's README-only first commit) is waiting for the default branch to
  be switched to `main` on GitHub, then `git push origin --delete master`.
- Not yet verified on real hardware: everything Pi-specific (rpicam-vid,
  GPIO keys, kmsdrm, backlight, sudo shutdown, scan speed on the Zero).
  A benchmark on the Pi is planned.
- `data/recognition/clip-vit-base-patch16.npz` only covers Gen 1; rebuild
  with `pokedex-embed --model clip-vit-base-patch16` before using it.
- Next ideas: caught tracking (scans mark Pokémon caught, counter on home),
  themes, shiny mode, read-aloud on request, About screen, brightness,
  voice search (I2S mic + Vosk/Whisper, matched by sound).
