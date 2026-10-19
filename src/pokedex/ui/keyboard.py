"""On-screen keyboard layout and D-pad movement across it."""

from dataclasses import dataclass

DELETE = "\b"
DONE = "\n"


@dataclass(frozen=True)
class Key:
    label: str
    value: str
    """Character typed, or DELETE / DONE."""
    span: int = 1
    """Width in grid columns."""


def _keys(chars: str) -> tuple[Key, ...]:
    return tuple(Key(c, c.lower()) for c in chars)


COLUMNS = 10
LAYOUT: tuple[tuple[Key, ...], ...] = (
    _keys("ABCDEFGHIJ"),
    _keys("KLMNOPQRST"),
    (*_keys("UVWXYZ"), Key("DEL", DELETE, span=2), Key("OK", DONE, span=2)),
    _keys("0123456789"),
)
DONE_POSITION = (2, 7)
"""Row and index of the OK key."""


def column_of(row: int, index: int) -> int:
    """Grid column where a key starts."""
    return sum(key.span for key in LAYOUT[row][:index])


def key_at_column(row: int, column: int) -> int:
    """Index of the key in row that covers column."""
    start = 0
    for index, key in enumerate(LAYOUT[row]):
        if start <= column < start + key.span:
            return index
        start += key.span
    return len(LAYOUT[row]) - 1


def move(row: int, index: int, d_row: int, d_col: int) -> tuple[int, int]:
    """Step the cursor, wrapping at every edge; vertical moves keep the column."""
    if d_col:
        index = (index + d_col) % len(LAYOUT[row])
    if d_row:
        column = column_of(row, index)
        row = (row + d_row) % len(LAYOUT)
        index = key_at_column(row, column)
    return row, index
