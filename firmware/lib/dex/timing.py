"""Screen sleep and button auto-repeat. Times are whole milliseconds."""


class ScreenSleep:
    """Turns the screen off after a few idle minutes; any press wakes it."""

    def __init__(self, now):
        self.last_input = now
        self.asleep = False

    def note_input(self, now):
        """Record a press; True if it woke the screen (the press then does nothing else)."""
        self.last_input = now
        if self.asleep:
            self.asleep = False
            return True
        return False

    def due(self, minutes, now):
        """True when the screen should go to sleep now."""
        return not self.asleep and minutes > 0 and now - self.last_input >= minutes * 60000


class Repeater:
    """Repeats a held D-pad direction, so scrolling 1,025 entries doesn't need 1,025 presses.

    The first repeat waits DELAY ms, then one fires every INTERVAL ms.
    """

    DELAY = 400
    INTERVAL = 120

    def __init__(self):
        self.action = None
        self._next = 0

    def press(self, action, now, repeats):
        """A button went down; only actions in repeats auto-repeat."""
        self.action = action if action in repeats else None
        self._next = now + self.DELAY

    def release(self, action):
        if action == self.action:
            self.action = None

    def due(self, now):
        """The held action if a repeat is due now, else None."""
        if self.action is None or now < self._next:
            return None
        self._next = now + self.INTERVAL
        return self.action
