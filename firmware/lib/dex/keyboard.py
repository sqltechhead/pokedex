"""On-screen keyboard layout and D-pad movement across it.

Each key is a tuple ``(label, value, span)``: the character it types (or
DELETE / DONE) and its width in grid columns.
"""

DELETE = "\b"
DONE = "\n"

LABEL, VALUE, SPAN = 0, 1, 2


def _keys(chars):
    return tuple((c, c.lower(), 1) for c in chars)


COLUMNS = 10
LAYOUT = (
    _keys("ABCDEFGHIJ"),
    _keys("KLMNOPQRST"),
    _keys("UVWXYZ") + (("DEL", DELETE, 2), ("OK", DONE, 2)),
    _keys("0123456789"),
)
DONE_POSITION = (2, 7)
"""Row and index of the OK key."""


def column_of(row, index):
    """Grid column where a key starts."""
    return sum(key[SPAN] for key in LAYOUT[row][:index])


def key_at_column(row, column):
    """Index of the key in row that covers column."""
    start = 0
    for index, key in enumerate(LAYOUT[row]):
        if start <= column < start + key[SPAN]:
            return index
        start += key[SPAN]
    return len(LAYOUT[row]) - 1


def move(row, index, d_row, d_col):
    """Step the cursor, wrapping at every edge; vertical moves keep the column."""
    if d_col:
        index = (index + d_col) % len(LAYOUT[row])
    if d_row:
        column = column_of(row, index)
        row = (row + d_row) % len(LAYOUT)
        index = key_at_column(row, column)
    return row, index
