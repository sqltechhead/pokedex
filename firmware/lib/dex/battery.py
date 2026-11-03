"""Battery voltage to the header's battery icon. Defaults match pins.py."""

FULL = 4.15
LOW = 3.45
EMPTY = 3.30


def fraction(volts, full=FULL, empty=EMPTY):
    """How full the icon is drawn, 0.0 to 1.0 (straight-line, which is close enough for an icon)."""
    return max(0.0, min(1.0, (volts - empty) / (full - empty)))


def is_low(volts, low=LOW):
    return volts < low
