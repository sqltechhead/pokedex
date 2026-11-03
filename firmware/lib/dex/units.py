"""Height and weight in metric or imperial, formatted the way the games show them.

Whole-number arithmetic throughout: the Pico's floats are single precision,
which would print 0.4 m as 0.4000001 m.
"""


def _tenths(value):
    """25 -> "2.5", 30 -> "3"."""
    whole, tenth = divmod(value, 10)
    return f"{whole}.{tenth}" if tenth else str(whole)


def format_height(height_dm, units):
    """4 dm -> "0.4 m" or "1'04\"" (inches rounded to the nearest)."""
    if units == "metric":
        return _tenths(height_dm) + " m"
    inches = (height_dm * 1000 + 127) // 254  # 1 dm = 100/2.54 in
    return f"{inches // 12}'{inches % 12:02d}\""


def format_weight(weight_hg, units):
    """60 hg -> "6 kg" or "13.2 lbs"."""
    if units == "metric":
        return _tenths(weight_hg) + " kg"
    tenths = (weight_hg * 220462 + 50000) // 100000  # 1 hg = 0.220462 lb
    return f"{tenths // 10}.{tenths % 10} lbs"
