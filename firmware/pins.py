# pins.py - pin map for the Pico 2 Pokédex handheld (CircuitPython)
# Matches the wiring diagram in plan.md. Pico 2, top view, USB at the top.
# Use these names everywhere instead of hard-coded pins, e.g.  import pins; pins.LCD_DC
import board

# Screen: Waveshare 3.5" Resistive Touch Display (G), ST7796S, 480 x 320, on SPI0
LCD_SCK = board.GP18    # screen cable pin 7  SCLK
LCD_MOSI = board.GP19   # screen cable pin 8  MOSI
LCD_MISO = board.GP16   # screen cable pin 9  MISO
LCD_CS = board.GP17     # screen cable pin 6  LCD_CS
LCD_DC = board.GP20     # screen cable pin 5  LCD_DC
LCD_RST = board.GP21    # screen cable pin 4  LCD_RST
LCD_BL = board.GP22     # screen cable pin 3  LCD_BL (PWM brightness, handled by the display driver)
LCD_BAUD = 40000000
LCD_WIDTH = 480
LCD_HEIGHT = 320

# Touch: XPT2046 on the same SPI bus as the screen, polled (TP_IRQ, cable pin 1, is not connected)
TP_CS = board.GP26      # screen cable pin 2  TP_CS
TP_BAUD = 2000000     # the touch controller needs a slow clock; lock the bus and reconfigure before reading

# microSD breakout on SPI1
SD_SCK = board.GP10
SD_MOSI = board.GP11
SD_MISO = board.GP12
SD_CS = board.GP13
SD_BAUD = 12000000
SD_MOUNT = "/sd"

# MAX98357A amplifier, I2S. Word select must be the pin after bit clock (GP1 = GP0 + 1).
I2S_BCLK = board.GP0    # BCLK
I2S_WS = board.GP1      # LRC
I2S_DATA = board.GP2    # DIN
AUDIO_RATE = 22050     # cries and voice clips: 22.05 kHz, 16-bit, mono WAV (set by pokedex-sdcard)

# Buttons: one leg to the pin, the other to GND. Pressed reads False (internal pull-up).
# The order here is the key_number that keypad.Keys reports.
BUTTON_NAMES = ("UP", "DOWN", "LEFT", "RIGHT", "A", "B", "START", "SELECT", "L", "R")
BUTTON_PINS = (
    board.GP3, board.GP4, board.GP5, board.GP6,   # D-pad
    board.GP7, board.GP8, board.GP9,              # A, B, Start
    board.GP14, board.GP15, board.GP27,           # Select, L, R
)

# Battery level: battery + -> 100 kOhm -> GP28 -> 100 kOhm -> GND
BATT_ADC = board.GP28
BATT_DIVIDER = 2.0
BATT_FULL_V = 4.15
BATT_LOW_V = 3.45       # show a low-battery warning below this
BATT_EMPTY_V = 3.30
