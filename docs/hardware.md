# Hardware

> [!IMPORTANT]
> **The [Pokédex Handheld Plan](https://claude.ai/artifact/UjDWTx9Sn6SvYG6ow1UfMZ) is the source of truth.** This page mirrors its hardware sections. If they ever disagree, the plan wins: update this page (and `firmware/pins.py`) to match. The plan also holds the wiring diagram and the 3D-printed case model, which aren't copied here.

> [!WARNING]
> **Not yet run on real hardware.** Run `hw_test.py` first (see [Build order](#build-order)) and expect to adjust the screen settings.

## Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Board | Raspberry Pi Pico 2 (RP2350, 520 KB RAM) | Cheap, in stock, boots instantly, long battery life |
| Language | CircuitPython 9 or later | Built-in displayio, keypad, SD and WAV playback keep the hardware code short |
| Screen | Waveshare 3.5" Resistive Touch Display (G): ST7796S + XPT2046, 480 × 320 | Thin enough for a 15 mm middle; 16-bit colour over SPI, so redraws are quick |
| Camera | Dropped | The Pico can't do image recognition usefully |
| Shape | Landscape, two-handed, with rounded grips | Easy for a child to hold; the screen is landscape anyway |
| Storage | microSD breakout on its own SPI bus | The (G) screen has no SD line on its cable |
| Sound | One MAX98357A amp, two 15 × 11 mm 8 Ω speakers in parallel | The sounds are mono, so one amp is enough |
| Case artwork | An original design | No official Pokémon or Pokédex designs on the case |

## Parts

Bought, with enough for **two builds**. "Per build" is what one handheld uses.

| Part | Per build | Size / notes |
| --- | --- | --- |
| Raspberry Pi Pico 2, **without headers** | 1 | 51 × 21 mm, flat, goes in the case. A Pico 2 **with headers** is for breadboard testing only |
| Waveshare 3.5" Resistive Touch Display (G), ST7796S + XPT2046, 11-pin GH1.25 cable | 1 | 85 × 56 mm board (assumed until measured) |
| Adafruit I2S 3W amp, MAX98357A | 1 | 19 × 18 × 2.6 mm |
| Adafruit microSD breakout, 3 V | 1 | 25.4 × 22.8 × 3.5 mm |
| 100 kΩ resistors | 2 | Battery-level divider |
| EEMB 3.7 V 1100 mAh 603449 LiPo, protection circuit, JST-PH 2.0 plug | 1 | About 6 × 34 × 49 mm |
| DollaTek Type-C USB 5 V 2 A boost charger (1S) | 1 | **Clip off the USB-A socket**; take 5 V from the 5V +/− pads |
| sourcing map 1 W 8 Ω speaker | 2 | 15 × 11 × 3.7 mm, **rectangular** |
| Gikfun tactile switches, 6 × 6 × 4.3 mm, through-hole | 10 | D-pad ×4, A, B, START, SELECT, L, R |
| SS12D00G3 slide switch | 1 | Power. Body 8.6 × 3.5 × 3.6 mm |
| 1N5819 Schottky diode | 1 | 5 V rail → Pico VSYS |
| JST-PH 2.0 2-pin plug/socket lead | 1 pair | Battery into the charger |
| Self-tapping screws, M2 / M2.5 pan head | 6 × M2.5×10, 8 × M2×5, 4 × M2×4 | |
| 1 mm double-sided foam tape | | Holds the battery, charger, amp and SD board |
| Heat-shrink, 22 AWG silicone wire, a multimeter | | |
| microSD card | 1 | 1 GB or more, **FAT32** (the full card is about 570 MB) |

**Wire colours:** black = GND, red = 5 V and battery +, yellow = D-pad, green = A/B/START/SELECT/L/R, blue = amp signals, white = SD and battery sense.

**Battery life estimate:** about 5–6 hours (Pico 2 about 25 mA, plus the backlight about 80 mA at 5 V through the boost).

## Pins

[`firmware/pins.py`](../firmware/pins.py) is the plan's pin map, and the firmware reads every pin from it. Pico 2 seen from the top, USB at the top.

| Function | GPIO | Pico pin | Other end |
| --- | --- | --- | --- |
| Amp BCLK | GP0 | 1 | MAX98357A BCLK |
| Amp LRC | GP1 | 2 | MAX98357A LRC (must be BCLK + 1) |
| Amp DIN | GP2 | 4 | MAX98357A DIN |
| Up | GP3 | 5 | switch → GND |
| Down | GP4 | 6 | switch → GND |
| Left | GP5 | 7 | switch → GND |
| Right | GP6 | 9 | switch → GND |
| A | GP7 | 10 | switch → GND |
| B | GP8 | 11 | switch → GND |
| START | GP9 | 12 | switch → GND |
| SD SCK | GP10 | 14 | SD breakout CLK |
| SD MOSI | GP11 | 15 | SD breakout DI |
| SD MISO | GP12 | 16 | SD breakout DO |
| SD CS | GP13 | 17 | SD breakout CS |
| SELECT | GP14 | 19 | switch → GND |
| L shoulder | GP15 | 20 | switch → GND |
| Screen MISO | GP16 | 21 | cable pin 9 |
| Screen CS | GP17 | 22 | cable pin 6 LCD_CS |
| Screen SCLK | GP18 | 24 | cable pin 7 |
| Screen MOSI | GP19 | 25 | cable pin 8 |
| Screen DC | GP20 | 26 | cable pin 5 LCD_DC |
| Screen RST | GP21 | 27 | cable pin 4 LCD_RST |
| Screen backlight | GP22 | 29 | cable pin 3 LCD_BL |
| Touch CS | GP26 | 31 | cable pin 2 TP_CS (held high: touch isn't used yet) |
| R shoulder | GP27 | 32 | switch → GND |
| Battery level | GP28 | 34 | middle of the 100 k / 100 k divider |
| 3.3 V out | 3V3 | 36 | SD breakout 3V |
| 5 V in | VSYS | 39 | from the 5 V rail through the Schottky diode (stripe towards the Pico) |
| GND | GND | 3, 8, 13, 18, 23, 28, 33, 38 | common ground |

Not connected: VBUS (40), 3V3_EN (37), ADC_VREF (35), RUN (30), screen TP_IRQ (cable pin 1).

## Wiring

**Power**

- Battery (JST-PH plug) → JST-PH socket lead → charger B+ / B−. Check the polarity with the multimeter first.
- Charger 5 V OUT+ → slide switch → **5 V rail**. Charger OUT− → common GND.
- 5 V rail → screen cable pin 11 (VCC), amp VIN, and through the Schottky diode to Pico VSYS (pin 39). The diode stops the Pico's USB feeding back into the boost board when you plug in to program it.
- Battery level: battery + (directly, before the switch) → 100 kΩ → GP28 → 100 kΩ → GND. GP28 reads half the battery voltage (at most 2.1 V).

**Screen (11-way GH1.25 cable):** pins 2–9 as in the pin map, 10 → GND, 11 → 5 V, pin 1 (TP_IRQ) unused. The touch controller shares SCLK/MOSI/MISO with the display.

**microSD breakout:** SCK/MOSI/MISO/CS to GP10–13, 3V to Pico pin 36, GND to GND.

**Amp:** BCLK/LRC/DIN to GP0/1/2, VIN to 5 V, GND to GND. GAIN and SD unconnected (9 dB, stereo mix). Both speakers in parallel on the amp's + and − (4 Ω total).

**Buttons:** each switch between its GPIO and GND; the firmware turns on the internal pull-ups.

**Ground:** all GNDs join together (charger OUT−, every Pico GND pin used, screen pin 10, amp, SD breakout, every button).

## Case

An original two-handed design, 176 × 78 mm, 15 mm thick in the middle and 26 mm at the grips, printed in PLA or PETG (about 55 g). The model, print settings and the measurements to check before printing are in the plan.

## Build order

1. Check the charger: battery in, measure 5 V on its output.
2. Flash CircuitPython onto the Pico 2 (README, "Set up the Pico 2").
3. Wire everything on the bench (not in the case). Copy `firmware/pins.py`, `firmware/st7796s.py` and `firmware/hw_test.py` to CIRCUITPY and run `import hw_test` from the serial console: it checks the buttons, screen, touch, microSD, audio and battery in turn.
4. Copy the app and the SD card (README) and run it on the bench.
5. Print the fit-test plate, then the full plate.
6. Assemble: face plate → switch plates and caps → shoulder caps and switches → slide switch → speakers → battery, SD and amp → charger → Pico → screen on its pillars → close with 6 screws.

## Safety (it's for a child)

- Protected LiPo (with a protection circuit) and a charger with protection; don't leave it charging unattended.
- Clip the charger's USB-A socket with nothing connected, and check 5V+ to − doesn't beep on continuity before first use.
- The case is screwed shut, so the battery can't be reached without a screwdriver.
- No magnets or loose small parts on the outside. Sand sharp print edges.
- If the charger cuts out when the load is very light, that's its auto power-off; with the backlight on it shouldn't trigger.
- **Speaker volume:** two 8 Ω speakers in parallel make 4 Ω, so the amp delivers more power. Start with **Volume** low.

## Things to check on first power-up

- **Screen orientation and colours** are set in `st7796s.py`: `_MADCTL = 0x28` (try `0x68`, `0xE8` or `0xA8` if the picture is mirrored or upside down) and inversion `0x21` (use `0x20` if colours look like a negative).
- **Touch** needs `hw_test.py`'s raw corner values before the app can use it.
- **Battery icon:** compare the header's level with the multimeter and `hw_test.py`'s reading. It turns yellow below 3.45 V (`pins.BATT_LOW_V`).
- **Card speed:** if sound stutters, try another microSD card, or lower `SD_BAUD` in `pins.py`.
