"""The parts of the handheld, built from the pin map in pins.py.

pins.py and st7796s.py sit at the top of the CIRCUITPY drive, alongside
hw_test.py, which checks each part on its own before the app runs.
"""

import analogio
import busio
import digitalio
import displayio
import keypad
import pins
import sdcardio
import storage
from audiobusio import I2SOut
from st7796s import make_display

from dex import state

SD_MOUNT = pins.SD_MOUNT
# What each button does, in pins.BUTTON_NAMES order (the key_number keypad reports).
BUTTON_ACTIONS = tuple(
    getattr(state, name) for name in pins.BUTTON_NAMES
)  # UP, DOWN, LEFT, RIGHT, A, B, START, SELECT, L, R

_touch_cs = None


def display():
    """The screen, refreshed by the app after each button press."""
    global _touch_cs
    displayio.release_displays()
    # The touch controller shares the screen's SPI bus: keep it deselected.
    _touch_cs = digitalio.DigitalInOut(pins.TP_CS)
    _touch_cs.switch_to_output(value=True)
    spi = busio.SPI(pins.LCD_SCK, MOSI=pins.LCD_MOSI, MISO=pins.LCD_MISO)
    screen = make_display(spi)
    screen.auto_refresh = False
    return screen


def mount_sd():
    """Mount the microSD card (writable, for settings); raises OSError if absent."""
    spi = busio.SPI(pins.SD_SCK, MOSI=pins.SD_MOSI, MISO=pins.SD_MISO)
    card = sdcardio.SDCard(spi, pins.SD_CS, baudrate=pins.SD_BAUD)
    storage.mount(storage.VfsFat(card), SD_MOUNT)


def buttons():
    """Debounced buttons; pressing one connects its pin to ground."""
    return keypad.Keys(pins.BUTTON_PINS, value_when_pressed=False, pull=True)


def audio_out():
    return I2SOut(pins.I2S_BCLK, pins.I2S_WS, pins.I2S_DATA)


class Backlight:
    """The screen's backlight (PWM, driven by displayio), off while the screen sleeps."""

    def __init__(self, screen):
        self._screen = screen

    def set(self, on, level=1.0):
        """level is the Brightness setting, 0.1-1.0."""
        self._screen.brightness = level if on else 0.0


class Battery:
    """The battery's voltage, through the 100k/100k divider on BATT_ADC."""

    def __init__(self):
        self._adc = analogio.AnalogIn(pins.BATT_ADC)

    def volts(self):
        raw = sum(self._adc.value for _ in range(16)) / 16  # average out the ADC's noise
        return raw * self._adc.reference_voltage / 65535 * pins.BATT_DIVIDER
