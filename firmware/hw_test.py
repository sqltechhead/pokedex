# hw_test.py - bring-up test for the Pico 2 Pokédex handheld (CircuitPython 9 or later)
# Copy to the CIRCUITPY drive: pins.py, st7796s.py and this file (rename it code.py to run on boot,
# or run it from the REPL with:  import hw_test).
# Tests, in order: buttons, screen, touch, microSD, audio, battery.
# Uses only modules built into CircuitPython - no extra libraries needed.
# Written against the plan; not yet run on the real hardware.

import time, math, array, os
import board, busio, digitalio, analogio, keypad, displayio, storage, sdcardio, audiobusio, audiocore
import pins
from st7796s import make_display


# ---------------------------------------------------------------- buttons
def test_buttons(seconds=10):
    keys = keypad.Keys(pins.BUTTON_PINS, value_when_pressed=False, pull=True)
    print("Buttons: press each one (", seconds, "s )")
    seen, end = set(), time.monotonic() + seconds
    while time.monotonic() < end:
        ev = keys.events.get()
        if ev and ev.pressed:
            name = pins.BUTTON_NAMES[ev.key_number]
            if name not in seen:
                seen.add(name); print("  pressed", name)
    keys.deinit()
    missing = [n for n in pins.BUTTON_NAMES if n not in seen]
    print("  not seen:", missing or "none")


# ---------------------------------------------------------------- screen (ST7796S via displayio)
displayio.release_displays()
spi0 = busio.SPI(pins.LCD_SCK, MOSI=pins.LCD_MOSI, MISO=pins.LCD_MISO)
tp_cs = digitalio.DigitalInOut(pins.TP_CS)
tp_cs.switch_to_output(value=True)          # keep touch deselected while the screen talks
display = None

def solid(colour):
    bmp = displayio.Bitmap(pins.LCD_WIDTH, pins.LCD_HEIGHT, 1)
    pal = displayio.Palette(1); pal[0] = colour
    return displayio.TileGrid(bmp, pixel_shader=pal)

def test_screen():
    global display
    display = make_display(spi0)
    display.auto_refresh = False
    for name, col in (("red", 0xFF0000), ("green", 0x00FF00), ("blue", 0x0000FF), ("white", 0xFFFFFF)):
        g = displayio.Group(); g.append(solid(col)); display.root_group = g
        t = time.monotonic(); display.refresh()
        print("Screen:", name, "full redraw %d ms" % ((time.monotonic() - t) * 1000))
        time.sleep(0.4)
    g = displayio.Group(); g.append(solid(0x000000))
    sq = displayio.Bitmap(40, 40, 1); p = displayio.Palette(1); p[0] = 0xFF0000
    g.append(displayio.TileGrid(sq, pixel_shader=p, x=0, y=0))
    display.root_group = g; display.refresh()
    print("Screen: a red square should be in the top-left corner")
    display.auto_refresh = True


# ---------------------------------------------------------------- touch (XPT2046, polled on the shared bus)
def _xpt(cmd, buf_out=bytearray(3), buf_in=bytearray(3)):
    buf_out[0] = cmd
    spi0.write_readinto(buf_out, buf_in)
    return ((buf_in[1] << 8) | buf_in[2]) >> 3

def touch_read():
    while not spi0.try_lock():
        pass
    try:
        spi0.configure(baudrate=pins.TP_BAUD, polarity=0, phase=0)
        tp_cs.value = False
        x, y, z = _xpt(0xD0), _xpt(0x90), _xpt(0xB0)
        tp_cs.value = True
    finally:
        spi0.unlock()          # the display reconfigures the bus to its own speed on its next refresh
    return x, y, z

def test_touch(seconds=8):
    print("Touch: tap the corners (", seconds, "s ). Raw values print below; use them to calibrate.")
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        x, y, z = touch_read()
        if z > 200:
            print("  raw x", x, "y", y, "pressure", z)
        time.sleep(0.08)


# ---------------------------------------------------------------- microSD
def test_sd():
    spi1 = busio.SPI(pins.SD_SCK, MOSI=pins.SD_MOSI, MISO=pins.SD_MISO)
    sd = sdcardio.SDCard(spi1, pins.SD_CS, baudrate=pins.SD_BAUD)
    storage.mount(storage.VfsFat(sd), pins.SD_MOUNT)
    print("SD: mounted, contents:", os.listdir(pins.SD_MOUNT)[:10])
    with open(pins.SD_MOUNT + "/hw_test.txt", "w") as f:
        f.write("ok")
    print("SD: write ok")


# ---------------------------------------------------------------- audio (MAX98357A over I2S)
def test_audio(freq=440, seconds=1.0):
    n = pins.AUDIO_RATE // freq
    wave = array.array("h", [int(8000 * math.sin(2 * math.pi * i / n)) for i in range(n)])
    tone = audiocore.RawSample(wave, sample_rate=pins.AUDIO_RATE)
    i2s = audiobusio.I2SOut(pins.I2S_BCLK, pins.I2S_WS, pins.I2S_DATA)
    print("Audio: playing a", freq, "Hz tone from both speakers")
    i2s.play(tone, loop=True); time.sleep(seconds); i2s.stop()
    i2s.deinit()
    # Playing a voice clip later is just:
    #   i2s.play(audiocore.WaveFile(open("/sd/voice/0025.wav", "rb")))


# ---------------------------------------------------------------- battery
def test_battery():
    adc = analogio.AnalogIn(pins.BATT_ADC)
    raw = sum(adc.value for _ in range(16)) / 16
    v = raw * adc.reference_voltage / 65535 * pins.BATT_DIVIDER
    adc.deinit()
    print("Battery: %.2f V" % v, "(LOW)" if v < pins.BATT_LOW_V else "")


test_buttons()
test_screen()
test_touch()
try:
    test_sd()
except Exception as e:
    print("SD: failed -", e)
test_audio()
test_battery()
print("Done.")
