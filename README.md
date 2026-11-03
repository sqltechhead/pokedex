<div align="center">

# Pokédex

**A real, working Pokédex for a 3D-printed handheld: a Raspberry Pi Pico 2 with a 3.5" screen, ten buttons, two speakers and a rechargeable battery.**<br>
Browse or search all 1,025 Pokémon, see their stats and evolutions, and hear each one's cry and its entry read aloud. Fully offline.

<br>

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?style=for-the-badge&logo=uv&logoColor=white)
![CircuitPython](https://img.shields.io/badge/CircuitPython-firmware-7B3FA0?style=for-the-badge)
![Raspberry Pi Pico 2](https://img.shields.io/badge/Raspberry_Pi-Pico_2-C51A4A?style=for-the-badge&logo=raspberrypi&logoColor=white)
![Works offline](https://img.shields.io/badge/works-offline-222222?style=for-the-badge)

[Features](#-features) ·
[Quick start](#-quick-start) ·
[How it works](#-how-it-works) ·
[Controls](#-controls) ·
[Settings](#%EF%B8%8F-settings) ·
[Development](#%EF%B8%8F-development)

</div>

> [!WARNING]
> **Not yet tested on real hardware.** The PC tools and the firmware's logic are tested, but the firmware hasn't run on a Pico yet. Expect to adjust the screen setup on first boot (see [docs/hardware.md](docs/hardware.md)).

> [!NOTE]
> **Hardware source of truth:** the [Pokédex Handheld Plan](https://claude.ai/artifact/UjDWTx9Sn6SvYG6ow1UfMZ) (parts, wiring, case). [docs/hardware.md](docs/hardware.md) mirrors it.

---

## ✨ Features

- 📖 **Browse all 1,025.** A scrolling list with a picture preview and type colours. L and R filter by type; holding the D-pad scrolls.
- 📊 **Full entries.** Artwork, types, height and weight, base stats and Pokédex text.
- 🧬 **Evolution chains.** Branches like Eevee's fan out with how each evolution happens ("Lv. 16", "Fire Stone"). Jump to any member.
- 🔎 **Search without a keyboard.** An on-screen keyboard for the D-pad, by name or number; "mrmime" finds Mr. Mime.
- 🔊 **Cries and narration.** Each entry plays the Pokémon's cry, then reads itself aloud: *"Pikachu, the Mouse Pokémon. When several of these Pokémon gather…"* SELECT plays it again.
- ⚙️ **Settings that stick.** Volume, sound, units and screen sleep, saved on the SD card.
- 🔋 **Battery friendly.** The screen only redraws what changed after a button press, and turns off when idle.
- 📴 **No network needed.** Everything is prepared on your computer once and read from a microSD card.

---

## 🚀 Quick start

### 1. Clone and install

Install [uv](https://docs.astral.sh/uv/) if you don't have it, then:

```sh
git clone https://github.com/<your-username>/pokedex.git
cd pokedex
uv sync
```

### 2. Get the data

> [!IMPORTANT]
> **The repository contains no Pokémon data.** It's git-ignored, and you build it yourself on your computer.

```sh
uv run pokedex-fetch --last 1025                # all 1,025 Pokémon from PokéAPI (or omit --last for Gen 1)
uv run --extra narrate pokedex-narrate          # optional: spoken entries
```

### 3. Build the SD card

```sh
uv run pokedex-sdcard                           # writes build/sd/pokedex/ (about 480 MB for all 1,025)
```

Copy the `pokedex` folder to the root of a **FAT32** microSD card. CircuitPython can't read exFAT, which is how most cards over 32 GB come formatted. Re-running only converts what's new.

### 4. Try it on your computer (optional)

No Pico yet? The simulator runs the real firmware in a 480×320 window, reading `build/sd` as its SD card:

```sh
uv run --group sim python sim/pokedex_sim.py
```

| Key | Button |
| --- | --- |
| Arrow keys | D-pad |
| Z or Enter | A |
| X, Backspace or Esc | B |
| Tab | SELECT |
| Space | START |
| Q / E | L / R |

It runs on Adafruit's desktop version of CircuitPython's display library, so layout, behaviour and sound match the device. Speed and memory don't: the real screen redraws much more slowly, and the Pico has far less RAM. `--shots folder/` clicks through a short tour and saves a screenshot of each screen.

### 5. Set up the Pico 2

1. **Install CircuitPython.** Download the `.uf2` for the **Raspberry Pi Pico 2** from [circuitpython.org](https://circuitpython.org/board/raspberry_pi_pico2/). Hold BOOTSEL while plugging the Pico in, then drag the file onto the `RP2350` drive. It restarts as a drive called `CIRCUITPY`.
2. **Install the two libraries the firmware uses:**
   ```sh
   uvx circup install -r firmware/requirements.txt
   ```
3. **Copy the firmware:**
   ```sh
   cp firmware/code.py firmware/pins.py firmware/st7796s.py firmware/hw_test.py /Volumes/CIRCUITPY/
   mkdir -p /Volumes/CIRCUITPY/lib && cp -R firmware/lib/dex /Volumes/CIRCUITPY/lib/
   ```
4. **Put the card in** and press reset. Wiring is in [docs/hardware.md](docs/hardware.md); on new hardware, run `import hw_test` from the serial console first.

To see errors while testing, open the Pico's serial console (for example `screen /dev/tty.usbmodem* 115200` on a Mac, or the serial panel in an editor like Thonny or Mu).

---

## 🧩 How it works

```text
Your computer                                    The Pico 2
───────────────────────────────                  ─────────────────────────────
pokedex-fetch    PokéAPI → data/pokedex.db       code.py → lib/dex/app.py
pokedex-narrate  Piper voice → data/narration/     reads /sd/pokedex/ only:
pokedex-sdcard   data/ → build/sd/pokedex/  ──SD──▶ index in RAM, entries,
                 (index, JSON, BMP, WAV, BDF)       pictures and sounds
                                                    streamed as needed
```

The Pico 2 has 520 KB of RAM and runs CircuitPython, so all the heavy lifting happens on the PC first:

| On the card | Made from | Why |
| --- | --- | --- |
| `index.tsv` | the database | Every name, number and type, small enough to keep in memory for the list and search |
| `mon/0025.json` | the database | One entry, read only when it's shown |
| `art/`, `spr/`, `ev72/` (and smaller) `0025.bmp` | official artwork (game sprites if missing) | 8-bit BMPs sized for each screen, which displayio streams straight from the card |
| `cry/`, `say/` `0025.wav` | cries and narration | Mono 16-bit WAV, which the Pico plays without decoding |
| `fonts/*.bdf` | DejaVu Sans | Bitmap fonts with only the characters used (including é, ♀ and the button arrows) |

---

## 🎮 Controls

| Button | Home | Search | Settings | List | Entry | Evolution |
| :---: | --- | --- | --- | --- | --- | --- |
| ▲▼ | Choose | Move on keyboard / results | Choose | Move (hold to scroll) | Prev / next | Between branches |
| ◀▶ | | Move on keyboard | Change value | Jump a page | Prev / next | Between stages |
| **A** | Open | Type key / open result | Flip switch | Open entry | Evolution chain | Open that entry |
| **B** | | Delete letter, then home | Back home | Clear filter, then home | Back to list or search | Back to entry |
| **SELECT** | | Jump to results | | | Play cry and entry again | |
| **L / R** | | | | Previous / next type filter | Back / forward 10 | |
| **START** | | Menu (home) from any screen | | | | |

The battery level shows at the top right of every screen, turning yellow when it's low.

---

## ⚙️ Settings

Changed on the device and saved to `settings.json` on the SD card.

| Setting | Options |
| --- | --- |
| **Volume**, **Sound**, **Cries**, **Read entries aloud** | What plays when an entry opens. |
| **Units** | Metric (1.7 m, 90.5 kg) or imperial (5'07", 199.5 lbs), as the games show them. |
| **Screen sleep** | Turn the backlight off after 1, 2, 5 or 10 idle minutes, or never. Any button wakes it, and that press does nothing else. |

---

## 🔊 Spoken entries

Entries are read aloud by [Piper](https://github.com/OHF-Voice/piper1-gpl), an offline text-to-speech engine, with a light "device" effect so it sounds like it comes from a gadget.

```sh
uv run --extra narrate pokedex-narrate                                  # new entries only
uv run --extra narrate pokedex-narrate --voice en_GB-cori-high --force  # another voice
uv run --extra narrate pokedex-narrate --clean --force                  # no effect
uv run pokedex-sdcard --force                                           # then rebuild the card
```

- **Voice:** `en_US-ryan-high` by default. Its licence allows personal, non-commercial use only. Any [Piper voice](https://huggingface.co/rhasspy/piper-voices) works and downloads to `data/voices/` the first time.
- **Pronunciation:** "Pokémon" is respelled so the voice says *POH-kay-mon*. Add any other word it gets wrong to `PRONUNCIATIONS` in [`script.py`](src/pokedex/narrator/script.py).

---

## 🛠️ Development

```sh
uv run --all-extras pytest            # tests (offline; the firmware's logic runs on the PC)
uv run ruff check . && uv run ruff format .
```

The firmware has to stay within the Python that CircuitPython supports: no `match`, dataclasses, enums or type hints. [`test_fw_compat.py`](tests/firmware/test_fw_compat.py) catches the common slips. The screens and main loop can be tried in the simulator; only `hardware.py`, `st7796s.py` and `audio.py` need the real device. Keep logic in the pure modules so the tests cover it.

<details>
<summary><b>Project layout</b></summary>

<br>

```
src/pokedex/            PC tools (CPython, managed by uv)
  models.py             Pokemon, BaseStats, EvolutionChain (Pydantic)
  db.py                 PokedexDB: the SQLite tables as Pokemon objects
  paths.py              DataPaths: where everything in data/ lives
  fetcher/              pokedex-fetch: PokéAPI client, records, evolution chains
  narrator/             pokedex-narrate: entry text, Piper voice, device effect
  sdcard/               pokedex-sdcard: index and entries, BMPs, WAVs, BDF fonts
firmware/               copied to the Pico's CIRCUITPY drive
  code.py               runs at power-on
  pins.py               pin map, from the Pokédex Handheld Plan
  st7796s.py            screen driver, from the plan
  hw_test.py            bring-up test for new hardware, from the plan
  requirements.txt      CircuitPython libraries (circup)
  lib/dex/
    app.py              main loop: buttons, sleep, audio, redraw
    state.py            navigation state and button actions (pure, tested)
    index.py            names, numbers and types in memory (pure, tested)
    records.py          entries and file paths on the card (pure, tested)
    search.py           name and number search (pure, tested)
    keyboard.py         on-screen keyboard layout (pure, tested)
    evolution.py        evolution stages from a chain (pure, tested)
    settings.py         settings and saving them (pure, tested)
    units.py            metric and imperial (pure, tested)
    timing.py           screen sleep and button repeat (pure, tested)
    battery.py          battery voltage to the header icon (pure, tested)
    screens.py          draws every screen with displayio
    audio.py            cry then narration over I2S
    hardware.py         the parts, built from pins.py: screen, SD, buttons, backlight, battery
    theme.py            colours and type colours
sim/                    runs the firmware on a PC in a window (not copied to the Pico)
tests/                  PC tests; tests/firmware/ covers the pure firmware modules
docs/hardware.md        parts, pins, wiring, build order (mirrors the plan)
```

</details>

<details>
<summary><b>What's in <code>data/</code></b></summary>

<br>

```
data/
  pokedex.db           SQLite: pokemon, evolution_chain, evolution
  sprites/0025.png     96×96 game sprite
  artwork/0025.png     475×475 official artwork
  cries/0025.ogg       modern cry (some are MP3 inside; ffmpeg reads both)
  narration/0025.ogg   spoken entry (pokedex-narrate)
  voices/              Piper voices (only for pokedex-narrate)
```

Query the database directly with `sqlite3 -header -column data/pokedex.db`.

</details>

---

## 🙏 Credits

- Pokémon data, sprites, artwork and cries from [**PokéAPI**](https://pokeapi.co), a free community API.
- Speech by [**Piper**](https://github.com/OHF-Voice/piper1-gpl); voice models from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- Firmware on [**CircuitPython**](https://circuitpython.org) with Adafruit's display_text and bitmap_font libraries.
- Text in [**DejaVu Sans**](https://dejavu-fonts.github.io/), whose licence is in [`src/pokedex/sdcard/fonts/`](src/pokedex/sdcard/fonts/).

<div align="center">
<sub>A personal fan project. Pokémon and Pokémon character names are trademarks of Nintendo, Creatures Inc. and GAME FREAK inc. This project is not affiliated with or endorsed by them.</sub>
</div>
