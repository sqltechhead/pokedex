# Hardware: shopping list and wiring

Everything needed to build the handheld Pokédex around a **Raspberry Pi Zero 2 W**.

> [!WARNING]
> **Not yet built.** This plan follows the software's needs and the boards' documentation, but none of it has been assembled or tested on real hardware yet. Check each part's own documentation, especially the screen's, before ordering, and expect to adjust.

## Shopping list

Everything is from **[The Pi Hut](https://thepihut.com)** (UK). Prices include VAT and were checked on **19 October 2026**. Prices and stock change often, and a few items were showing as sold out, so check each page before ordering. Delivery isn't included.

### 1. The handheld

| Part | Product | Price | Notes |
| --- | --- | ---: | --- |
| Computer | [Raspberry Pi Zero 2 W](https://thepihut.com/products/raspberry-pi-zero-2) | £14.40 | Choose the **pre-soldered header** option, which may cost a little more. Not the older "Zero WH" |
| Storage | [Raspberry Pi microSD card, OS pre-installed](https://thepihut.com/products/noobs-preinstalled-sd-card) | ~£10 * | Pick **32 GB**, then reflash it with Raspberry Pi OS **Lite** (64-bit) |
| Screen | [Waveshare 3.5" Resistive Touch Display (G)](https://thepihut.com/products/3-5-resistive-touch-display-g-for-raspberry-pi-320x480) | £15.40 | 480×320 IPS panel, ST7796S chip, XPT2046 touch, backlight pin. **Connect it with its 11-wire cable, not the pogo pins** (see below). Easier-to-set-up alternative: [Adafruit 3.5" HXD8357D breakout](https://thepihut.com/products/adafruit-3-5-tft-320x480-touchscreen-breakout-board-w-microsd-socket), £38.40 |
| Camera | [Raspberry Pi Camera Module 3](https://thepihut.com/products/raspberry-pi-camera-module-3) | £24.00 | Standard lens, not NoIR |
| Camera cable | [Pi Zero "Stub" Camera Cable, 38 mm](https://thepihut.com/products/raspberry-pi-zero-stub-camera-cable-38mm) | £2.50 | For a camera mounted right next to the Pi |
| Amplifier | [Adafruit I2S 3W Amplifier, MAX98357A](https://thepihut.com/products/adafruit-i2s-3w-class-d-amplifier-breakout-max98357a) | £5.70 | If sold out: [MAX98357 I2S Amplifier Module](https://thepihut.com/products/max98357-i2s-amplifier-module) |
| Speaker | [1" Mini Metal Speaker, 8 Ω 0.5 W](https://thepihut.com/products/mini-metal-speaker-w-wires-8-ohm-0-5w) | £2.00 | 28 mm, 6 g. See the volume warning below |
| Buttons | [Soft Silicone Top 6 mm Push-buttons, 20-pack](https://thepihut.com/products/soft-silicone-top-6mm-push-buttons-20-pack) | £2.50 | 8 needed. Or the plain [6 mm 20-pack](https://thepihut.com/products/tactile-button-switch-6mm-x-20-pack) (£2.20) when in stock |
| Charger and booster | [PowerBoost 1000C](https://thepihut.com/products/adafruit-powerboost-1000-charger-rechargeable-5v-lipo-usb-boost-1a) | £19.20 | Charges over micro-USB while running. Was sold out when checked |
| Battery | [2000mAh 3.7V LiPo, JST-PH](https://thepihut.com/products/2000mah-3-7v-lipo-battery) | £10.00 | 60 × 38 × 8 mm, built-in protection. Check polarity against the PowerBoost |
| Power switch | [Breadboard-friendly SPDT Slide Switch](https://thepihut.com/products/breadboard-friendly-spdt-slide-switch) | £0.80 | |
| | | **£106.50** | |

\* Estimated: the listing's £30.60 appears to be for a larger card. Check the 32 GB price on the page.

### 2. Building

| Part | Product | Price | Notes |
| --- | --- | ---: | --- |
| Wire | 30 AWG silicone, 2 m each: [black](https://thepihut.com/products/silicone-cover-stranded-core-wire-2m-30awg-black), [red](https://thepihut.com/products/silicone-cover-stranded-core-wire-2m-30awg-red), [white](https://thepihut.com/products/silicone-cover-stranded-core-wire-2m-30awg-white), [yellow](https://thepihut.com/products/silicone-cover-stranded-core-wire-2m-30awg-yellow) | £3.20 | £0.80 each |
| Shell inserts | [Brass Heat-Set Inserts, M3 × 4 mm, 50-pack](https://thepihut.com/products/brass-heat-set-inserts-for-plastic-m3-x-4mm-50-pack) | £5.90 | Design the shell's screw points for M3 |
| Insert tool | [Heat-set insert tip for soldering irons, M3](https://thepihut.com/products/heat-set-insert-for-soldering-irons-4-40-m3-inserts) | £10.80 | Fits Hakko-style irons. Optional, but makes inserts go in straight |
| Mounting the Pi | [White Nylon Screw and Stand-off Set, M2.5](https://thepihut.com/products/white-nylon-screw-and-stand-off-set-m2-5-thread) | £13.00 | 420 pieces; the Pi's holes are M2.5 |
| Heat-shrink | [Wire and heat-shrink range](https://thepihut.com/collections/prototyping-wire-heat-shrink) | — | Any small assortment |
| | | **£32.90** | |

Also needed, if you don't already have them: a soldering iron and solder, flush cutters, a multimeter, and access to a 3D printer.

### 3. Setting up and prototyping

| Part | Product | Price | Notes |
| --- | --- | ---: | --- |
| Screen for setup | [Mini-HDMI to HDMI adapter cable](https://thepihut.com/products/official-raspberry-pi-mini-hdmi-male-to-hdmi-female-adapter-cable) | £2.30 | Plug the Zero into a monitor for first setup. A micro-USB OTG adapter (for a keyboard) is in the [adapters range](https://thepihut.com/collections/raspberry-pi-cable-adapters-accessories); or set it up over SSH instead |
| Breadboard | [Half Size Breadboard + 78 Jumper Wires](https://thepihut.com/products/adafruit-half-size-breadboard-78-piece-22awg-jumper-wire-bundle) | £9.60 | Try the screen, buttons and amplifier before soldering |
| Jumper wires | [Female/Male jumper wires, 20 × 6"](https://thepihut.com/products/premium-female-male-extension-jumper-wires-20-x-6) | £1.70 | From the Pi's header to the breadboard |
| | | **£13.60** | |

### Total

| | Price |
| --- | ---: |
| 1. The handheld | £106.50 |
| 2. Building | £32.90 |
| 3. Setting up and prototyping | £13.60 |
| **Everything** | **£153.00** |

Skipping the optional insert tip brings it to **£142.20**. Choosing the Adafruit screen instead adds £23. Add delivery, heat-shrink and an OTG adapter on top.

### Optional extras (not in the totals)

| Part | Why |
| --- | --- |
| White LED and resistor | Lights the subject for scanning in dim rooms (needs a small code addition) |
| MAX17048 LiPo fuel gauge (I2C) | A battery level on screen (needs code) |
| INMP441 I2S microphone | For voice search later. Shares the audio pins with the amplifier |

### Before you plug anything in

> [!WARNING]
> **Speaker volume:** the amplifier can deliver nearly 2 W into this 0.5 W speaker and could blow it at full volume. Wire the amplifier's GAIN pin for its lowest gain (see Adafruit's guide), or keep **Volume** below about 50% until you've tested it.

> [!WARNING]
> **Battery polarity:** check that the battery's red wire lines up with the **+** marking on the PowerBoost before connecting. A reversed plug can destroy the board.

## Pin plan

One layout where everything fits together on the 40-pin header (BCM GPIO numbers).

| Function | GPIO | Header pin |
| --- | --- | --- |
| Screen SPI MOSI | 10 | 19 |
| Screen SPI clock | 11 | 23 |
| Screen chip select (CE0) | 8 | 24 |
| Screen SPI MISO (touch only) | 9 | 21 |
| Screen data/command (DC) | 24 | 18 |
| Screen reset | 25 | 22 |
| Screen backlight | 12 | 32 |
| Touch chip select (CE1, optional) | 7 | 26 |
| Touch interrupt (optional) | 17 | 11 |
| I2S bit clock (amp, mic) | 18 | 12 |
| I2S word select (amp, mic) | 19 | 35 |
| I2S data out (to amp) | 21 | 40 |
| I2S data in (from mic, optional) | 20 | 38 |
| Button **Up** | 5 | 29 |
| Button **Down** | 6 | 31 |
| Button **Left** | 13 | 33 |
| Button **Right** | 26 | 37 |
| Button **A** | 16 | 36 |
| Button **B** | 23 | 16 |
| Button **SELECT** | 22 | 15 |
| Button **START** | 27 | 13 |
| Fuel gauge SDA / SCL (optional) | 2 / 3 | 3 / 5 |
| Scanner LED (optional) | 4 | 7 |
| *Left free: serial console* | 14 / 15 | 8 / 10 |

Power: the booster's 5 V output goes to header pin 2 (5 V) and its ground to pin 6. The screen and amplifier take 3.3 V or 5 V as their boards specify. Each button goes between its GPIO and any ground pin; the Pi's internal pull-ups do the rest.

## Configuration

Add to `/boot/firmware/config.txt` on the Pi:

```ini
# Buttons as keys (see the README's controls table)
dtoverlay=gpio-key,gpio=5,active_low=1,gpio_pull=up,keycode=103,label=up
dtoverlay=gpio-key,gpio=6,active_low=1,gpio_pull=up,keycode=108,label=down
dtoverlay=gpio-key,gpio=13,active_low=1,gpio_pull=up,keycode=105,label=left
dtoverlay=gpio-key,gpio=26,active_low=1,gpio_pull=up,keycode=106,label=right
dtoverlay=gpio-key,gpio=16,active_low=1,gpio_pull=up,keycode=28,label=a
dtoverlay=gpio-key,gpio=23,active_low=1,gpio_pull=up,keycode=1,label=b
dtoverlay=gpio-key,gpio=22,active_low=1,gpio_pull=up,keycode=15,label=select
dtoverlay=gpio-key,gpio=27,active_low=1,gpio_pull=up,keycode=59,label=start

# Sound through the MAX98357A
dtparam=audio=off
dtoverlay=max98357a

# Screen: SPI on, then the overlay for your screen's controller
dtparam=spi=on
```

**The screen needs its own overlay.** Use the kernel's DRM drivers rather than the older `fbtft` ones, so pygame can draw with `SDL_VIDEODRIVER=kmsdrm` as the README describes.

- **Waveshare (G), ST7796S:** use the generic `mipi-dbi-spi` overlay with an init file of the ST7796S's startup commands, with its DC, reset and backlight pins set to the pin plan (24, 25 and 12), and rotated to landscape (the panel is portrait, 320×480). Touch uses the `ads7846` overlay on CE1 with its interrupt on GPIO 17. Waveshare's own guide covers their older driver, so this step is the one to test first.
- **Adafruit HXD8357D:** the kernel has a driver made for this chip, which makes setup simpler.

#### Wiring the Waveshare (G)

It can connect two ways. **Use the 11-wire GH1.25 cable**, wired to the pin plan above. Its pogo-pin option presses onto the Pi's header with fixed pins, and puts the backlight on GPIO 18, which the audio amplifier needs.

## Things to check when building

- **Screen speed:** SPI screens refresh more slowly than HDMI. Menus and entries only redraw on a button press, so that's fine; the scanner's live preview runs at about 15 frames a second, which should be within reach.
- **Power draw:** the Zero 2 W with screen, camera and amplifier can peak near 1 A while scanning. Check the booster's rating, and watch for the Pi's low-voltage warning.
- **Heat:** sustained scanning makes the Zero throttle in a closed shell. A few vent slots near the processor help.
- **Camera orientation:** if it ends up upside down, turn on **Settings → Camera upside down** rather than reprinting the shell.
- **Shut down before switching off:** use **Settings → Shut down**, wait for the green activity LED to stop, then flip the power switch.
