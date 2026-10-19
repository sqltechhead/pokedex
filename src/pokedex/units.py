"""Height and weight in metric or imperial, formatted the way the games show them."""

from typing import Literal

Units = Literal["metric", "imperial"]

CM_PER_INCH = 2.54
LB_PER_KG = 2.20462


def format_height(height_dm: int, units: Units) -> str:
    """4 dm -> "0.4 m" or "1'04\""."""
    if units == "metric":
        return f"{height_dm / 10:g} m"
    inches = round(height_dm * 10 / CM_PER_INCH)
    return f"{inches // 12}'{inches % 12:02d}\""


def format_weight(weight_hg: int, units: Units) -> str:
    """60 hg -> "6 kg" or "13.2 lbs"."""
    if units == "metric":
        return f"{weight_hg / 10:g} kg"
    return f"{weight_hg / 10 * LB_PER_KG:.1f} lbs"
