# st7796s.py - minimal displayio driver for the ST7796S (Waveshare 3.5" (G)), CircuitPython 9 or later
# Usage:
#   import displayio, busio, pins
#   from st7796s import make_display
#   displayio.release_displays()
#   spi = busio.SPI(pins.LCD_SCK, MOSI=pins.LCD_MOSI, MISO=pins.LCD_MISO)
#   display = make_display(spi)
# Written against the datasheet and the plan; not yet run on the real screen.

try:                                   # CircuitPython 9+
    from fourwire import FourWire
    from busdisplay import BusDisplay
except ImportError:                    # CircuitPython 8
    from displayio import FourWire
    from displayio import Display as BusDisplay

import pins

# Init sequence format: command, (number of data bytes | 0x80 if a delay follows), data..., [delay ms]
_MADCTL = 0x28   # landscape (MV) + BGR. If the picture is mirrored or upside down try 0x68, 0xE8 or 0xA8.
_INIT = bytes((
    0x01, 0x80, 150,          # software reset, wait 150 ms
    0x11, 0x80, 150,          # sleep out, wait 150 ms
    0x3A, 0x01, 0x55,         # 16-bit colour (RGB565)
    0x36, 0x01, _MADCTL,      # orientation
    0x21, 0x00,               # inversion on (IPS panels need it; use 0x20 if colours look like a negative)
    0x13, 0x00,               # normal display mode
    0x29, 0x80, 50,           # display on, wait 50 ms
))


class ST7796S(BusDisplay):
    def __init__(self, bus, **kwargs):
        super().__init__(bus, _INIT, **kwargs)


def make_display(spi, brightness=1.0):
    """Create the 480 x 320 landscape display on an existing busio.SPI."""
    bus = FourWire(spi, command=pins.LCD_DC, chip_select=pins.LCD_CS,
                   reset=pins.LCD_RST, baudrate=pins.LCD_BAUD)
    return ST7796S(bus, width=pins.LCD_WIDTH, height=pins.LCD_HEIGHT,
                   backlight_pin=pins.LCD_BL, brightness=brightness)
