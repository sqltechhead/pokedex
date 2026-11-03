"""Who's that Pokémon? A silhouette and four names to choose from.

Works on index positions (see dex.index). rand(n) returns a whole number
from 0 to n - 1: random.randrange on the Pico, a seeded one in the tests.
"""

CHOICES = 4


class Quiz:
    def __init__(self, dex, rand):
        self.dex = dex
        self._rand = rand
        self.score = 0
        self.asked = 0
        self.target = None
        """Index position of the Pokémon to guess."""
        self.choices = []
        """Index positions of the names offered, the target among them."""
        self.cursor = 0
        self.answer = None
        """Which choice was picked, once answered."""
        self.new_question()

    @property
    def answered(self):
        return self.answer is not None

    @property
    def correct(self):
        return self.answered and self.choices[self.answer] == self.target

    def new_question(self):
        n = len(self.dex)
        self.answer = None
        self.cursor = 0
        if not n:
            self.target, self.choices = None, []
            return
        previous = self.target
        self.target = self._rand(n)
        if self.target == previous and n > 1:  # never the same Pokémon twice in a row
            self.target = (self.target + 1 + self._rand(n - 1)) % n
        choices = [self.target]
        while len(choices) < min(CHOICES, n):
            pick = self._rand(n)
            if pick not in choices:
                choices.append(pick)
        for i in range(len(choices) - 1, 0, -1):  # shuffle, so the answer isn't always first
            j = self._rand(i + 1)
            choices[i], choices[j] = choices[j], choices[i]
        self.choices = choices

    def move(self, delta):
        if self.choices and not self.answered:
            self.cursor = (self.cursor + delta) % len(self.choices)

    def choose(self, index=None):
        """Answer with the given choice (the cursor's by default); True if right."""
        if self.answered or not self.choices:
            return False
        self.answer = self.cursor if index is None else index
        self.cursor = self.answer
        self.asked += 1
        if self.correct:
            self.score += 1
        return self.correct
