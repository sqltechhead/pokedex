"""Navigation state: what the buttons do on each screen.

No hardware imports, so the tests run it on a PC. The list works on index
positions (see dex.index) rather than Pokémon objects, to keep RAM use small;
full entries are read from the SD card only when shown.
"""

from dex import evolution, keyboard
from dex.index import REGIONS
from dex.quiz import Quiz
from dex.search import search
from dex.settings import KEY, KIND, Settings
from dex.settings import ROWS as SETTING_ROWS

# The physical buttons: a D-pad, A, B, SELECT, START and the L/R shoulders.
UP, DOWN, LEFT, RIGHT, A, B, SELECT, START, L, R = range(10)
DPAD = (UP, DOWN, LEFT, RIGHT)
JUMP = 10
"""How far L/R move on an entry."""

# Screens.
HOME, LIST, DETAIL, EVOLUTION, SEARCH, SETTINGS, QUIZ, BROWSE = range(8)

# Home screen entries, top to bottom, and the screen each opens.
MENU = (
    ("POKÉDEX", LIST),
    ("SEARCH", SEARCH),
    ("BROWSE", BROWSE),
    ("QUIZ", QUIZ),
    ("SETTINGS", SETTINGS),
)

# Tabs on an entry, switched with LEFT/RIGHT.
INFO, MATCHUPS, ABILITIES, MOVES = range(4)
TABS = ("INFO", "TYPES", "ABILITIES", "MOVES")


def _default_rand():
    import random  # here, so the tests can run without touching the global generator

    return random.randrange


MAX_QUERY = 12


class SearchState:
    """The search screen: a query typed on the on-screen keyboard and its results.

    The cursor is either on the keyboard or, after OK, in the results list.
    """

    def __init__(self, dex):
        self.dex = dex
        self.query = ""
        self.results = []
        """Index positions of the matches."""
        self.in_results = False
        self.key_row = 0
        self.key_index = 0
        self.result_index = 0

    @property
    def key(self):
        return keyboard.LAYOUT[self.key_row][self.key_index]

    @property
    def selected(self):
        """Index position of the highlighted result, or None."""
        return self.results[self.result_index] if self.results else None

    def set_query(self, query):
        self.query = query[:MAX_QUERY]
        self.results = search(self.dex, self.query)
        self.result_index = 0
        if not self.results:
            self.in_results = False

    def type(self, text):
        self.set_query(self.query + text)

    def backspace(self):
        """Delete the last character; False if there was nothing to delete."""
        if not self.query:
            return False
        self.set_query(self.query[:-1])
        return True

    def press(self, row, index):
        """Press an on-screen key (also moves the cursor there)."""
        self.key_row, self.key_index = row, index
        value = self.key[keyboard.VALUE]
        if value == keyboard.DELETE:
            self.backspace()
        elif value == keyboard.DONE:
            self.in_results = bool(self.results)
        else:
            self.type(value)

    def move_key(self, d_row, d_col):
        self.key_row, self.key_index = keyboard.move(self.key_row, self.key_index, d_row, d_col)

    def move_result(self, delta):
        if self.results:
            self.result_index = (self.result_index + delta) % len(self.results)


class PokedexState:
    def __init__(self, dex, entry=None, settings=None, rand=None, browse=None):
        """entry(pokemon_id) returns a full entry dict or None (dex.records.Records.entry).

        rand(n) picks the quiz's Pokémon (see dex.quiz). browse is a dex.browse.Browse,
        or None when the card has no categories.
        """
        self.dex = dex
        self._entry = entry or (lambda pokemon_id: None)
        self.settings = settings or Settings()
        self.view = HOME
        self.menu_index = 0
        """Home screen selection; kept so the menu remembers the last choice."""
        self.settings_index = 0
        self.page_size = 9
        """How far LEFT/RIGHT jump in the list; the screen sets it to the visible rows."""
        self.detail_return = LIST
        """Where B goes from an entry: the list, or the search it was opened from."""
        self.type_filter = None
        self.region_filter = 0
        """Generation shown in the list, or 0 for every region."""
        self.visible = list(range(len(dex)))
        """Index positions shown in the list (all, or those matching the filters)."""
        self.index = 0
        """Position of the selection within visible."""
        self.evo_stage = 0
        self.evo_row = 0
        """Evolution screen cursor: column (stage) and row within it."""
        self.replay = False
        """SELECT on an entry asks for its cry and narration again; the app clears it."""
        self.tab = INFO
        """The entry's tab. Every entry opens on INFO, including the next one."""
        self.move_scroll = 0
        self.move_rows = 11
        """Moves that fit on the MOVES tab; the screen sets it."""
        self.quiz_sound = None
        """"correct" or "wrong" once a quiz question is answered; the app plays and clears it."""
        self.available_types = dex.type_names()
        self.available_regions = dex.regions()
        self.search = SearchState(dex)
        self._rand = rand
        self.quiz = None
        """Made the first time the quiz opens, then kept so the score carries on."""
        self.browse = browse
        self.browse_slug = None
        """The category whose values are shown, or None for the list of categories."""
        self.browse_index = 0
        """Cursor in the list of categories; 0 is the "Show" row above them."""
        self.value_index = 0
        self.value_rows = 8
        """Values that fit on the browse screen; the screen sets it. LEFT/RIGHT page by it."""

    # What is selected

    @property
    def selected(self):
        """Index position of the selected Pokémon, or None if the list is empty."""
        return self.visible[self.index] if self.visible else None

    @property
    def selected_id(self):
        pos = self.selected
        return None if pos is None else self.dex.ids[pos]

    @property
    def entry(self):
        """The selected Pokémon's full entry from the SD card, or None."""
        pokemon_id = self.selected_id
        return None if pokemon_id is None else self._entry(pokemon_id)

    @property
    def chain(self):
        entry = self.entry
        return entry.get("chain") if entry else None

    @property
    def stages(self):
        return evolution.stages(self.chain)

    @property
    def evo_cursor(self):
        """Species ID under the evolution screen cursor."""
        stages = self.stages
        return stages[self.evo_stage][self.evo_row] if stages else None

    # Buttons

    def handle(self, action):
        if action == START:  # the menu, from anywhere
            self.view = HOME
            return
        handler = (
            self._handle_home,
            self._handle_list,
            self._handle_detail,
            self._handle_evolution,
            self._handle_search,
            self._handle_settings,
            self._handle_quiz,
            self._handle_browse,
        )[self.view]
        handler(action)

    def _handle_home(self, action):
        if action == UP:
            self.menu_index = (self.menu_index - 1) % len(MENU)
        elif action == DOWN:
            self.menu_index = (self.menu_index + 1) % len(MENU)
        elif action == A:
            self.open_menu(self.menu_index)

    def open_menu(self, index):
        self.menu_index = index
        self.view = MENU[index][1]
        self.settings_index = 0
        if self.view == LIST:  # the Pokédex always opens at #001, with nothing filtered
            if self.browse:
                self.browse.clear()
            self.set_filter(None, 0)
            self.index = 0
        elif self.view == QUIZ:
            if self.quiz is None:
                self.quiz = Quiz(self.dex, self._rand or _default_rand())
            elif self.quiz.answered:
                self.quiz.new_question()

    def _handle_list(self, action):
        if action == UP:
            self._step(-1)
        elif action == DOWN:
            self._step(1)
        elif action == LEFT:
            self._jump(-self.page_size)
        elif action == RIGHT:
            self._jump(self.page_size)
        elif action == A and self.visible:
            self._show_entry()
            self.detail_return = LIST
        elif action == B and self.filtered:
            if self.browse:
                self.browse.clear()
            self.set_filter(None, 0)
        elif action == B:
            self.view = HOME
        elif action == L:
            self.cycle_filter(-1)
        elif action == R:
            self.cycle_filter(1)
        elif action == SELECT:
            self.cycle_region()

    def _handle_detail(self, action):
        if self.tab == MOVES and action in (UP, DOWN):
            self.scroll_moves(-1 if action == UP else 1)
        elif action == UP:
            self._step(-1)
        elif action == DOWN:
            self._step(1)
        elif action in (LEFT, RIGHT):
            self.tab = (self.tab + (1 if action == RIGHT else -1)) % len(TABS)
            self.move_scroll = 0
        elif action == A:
            self.open_evolution()
        elif action == B:
            self.view = self.detail_return
        elif action == SELECT:
            self.replay = True
        elif action == L:
            self._jump(-JUMP)
        elif action == R:
            self._jump(JUMP)

    def _handle_evolution(self, action):
        if action == UP:
            self.move_evo_cursor(self.evo_stage, self.evo_row - 1)
        elif action == DOWN:
            self.move_evo_cursor(self.evo_stage, self.evo_row + 1)
        elif action == LEFT:
            self.move_evo_cursor(self.evo_stage - 1, self.evo_row)
        elif action == RIGHT:
            self.move_evo_cursor(self.evo_stage + 1, self.evo_row)
        elif action == A and self.evo_cursor is not None:
            self.open_species(self.evo_cursor)
        elif action == B:
            self._show_entry()

    def _handle_search(self, action):
        s = self.search
        if s.in_results:
            if action == UP:
                s.move_result(-1)
            elif action == DOWN:
                s.move_result(1)
            elif action == A and s.selected is not None:
                self.open_species(self.dex.ids[s.selected], return_to=SEARCH)
            elif action in (B, LEFT, SELECT):
                s.in_results = False
            return
        if action == UP:
            s.move_key(-1, 0)
        elif action == DOWN:
            s.move_key(1, 0)
        elif action == LEFT:
            s.move_key(0, -1)
        elif action == RIGHT:
            s.move_key(0, 1)
        elif action == A:
            s.press(s.key_row, s.key_index)
        elif action == B and not s.backspace():
            self.view = HOME
        elif action == SELECT:
            s.in_results = bool(s.results)

    def _handle_settings(self, action):
        row = SETTING_ROWS[self.settings_index]
        if action in (UP, DOWN):
            step = -1 if action == UP else 1
            self.settings_index = (self.settings_index + step) % len(SETTING_ROWS)
        elif action in (LEFT, RIGHT):
            self.change_setting(self.settings_index, -1 if action == LEFT else 1)
        elif action == A and row[KIND] != "slider":
            self.change_setting(self.settings_index, 1)
        elif action == B:
            self.view = HOME

    def _handle_quiz(self, action):
        quiz = self.quiz
        if action == B or quiz is None:
            self.view = HOME
        elif quiz.answered:
            if action == A:
                quiz.new_question()
        elif action in (UP, DOWN):
            quiz.move(-1 if action == UP else 1)
        elif action == A and quiz.choices:
            self.quiz_sound = "correct" if quiz.choose() else "wrong"

    def _handle_browse(self, action):
        browse = self.browse
        if browse is None or not browse.categories:
            if action == B:
                self.view = HOME
            return
        if self.browse_slug is None:
            shown = browse.shown_categories()
            rows = len(shown) + 1
            self.browse_index = min(self.browse_index, rows - 1)
            if action in (UP, DOWN):
                self.browse_index = (self.browse_index + (1 if action == DOWN else -1)) % rows
            elif action == A and self.browse_index == 0:
                self.view = LIST  # the list, narrowed to the picks
                self.index = 0
            elif action == A:
                self.browse_slug = shown[self.browse_index - 1][0]
                self.value_index = 0
            elif action == SELECT:
                browse.clear()
                self.set_filter(self.type_filter)
            elif action == B:
                self.view = HOME
            return
        shown = self.shown_values
        if action == B:
            self._back_to_categories()
        elif not shown:
            return
        elif action in (UP, DOWN):
            self.value_index = (self.value_index + (1 if action == DOWN else -1)) % len(shown)
        elif action in (LEFT, RIGHT):
            step = self.value_rows if action == RIGHT else -self.value_rows
            self.value_index = max(0, min(len(shown) - 1, self.value_index + step))
        elif action in (L, R):
            values = browse.values(self.browse_slug)
            labels = [values[k][0] for k in shown]
            step = 1 if action == R else -1
            self.value_index = browse.letter_jump(labels, self.value_index, step)
        elif action == A:
            browse.toggle(self.browse_slug, shown[self.value_index])
            self.set_filter(self.type_filter)

    @property
    def shown_values(self):
        """Value numbers listed for the open category (see Browse.shown_values)."""
        return self.browse.shown_values(self.browse_slug) if self.browse_slug else []

    def _back_to_categories(self):
        """Close the category, keeping the cursor on it (the list may have shrunk)."""
        slugs = [c[0] for c in self.browse.shown_categories()]
        slug, self.browse_slug = self.browse_slug, None
        self.browse_index = slugs.index(slug) + 1 if slug in slugs else 0

    @property
    def filtered(self):
        """True when any filter (type, region or browse picks) narrows the list."""
        picked = self.browse is not None and self.browse.count
        return bool(self.type_filter or self.region_filter or picked)

    def scroll_moves(self, delta):
        entry = self.entry
        total = len(entry.get("moves") or ()) if entry else 0
        self.move_scroll = max(0, min(max(0, total - self.move_rows), self.move_scroll + delta))

    def change_setting(self, row, delta):
        self.settings_index = row
        self.settings = self.settings.adjusted(SETTING_ROWS[row][KEY], delta)

    # Moving around

    def open_evolution(self):
        """Show the selected Pokémon's chain with the cursor on it."""
        pokemon_id = self.selected_id
        if pokemon_id is None:
            return
        self.view = EVOLUTION
        self.evo_stage = self.evo_row = 0
        for stage, species_ids in enumerate(self.stages):
            if pokemon_id in species_ids:
                self.evo_stage, self.evo_row = stage, species_ids.index(pokemon_id)

    def move_evo_cursor(self, stage, row):
        """Move within the chain, keeping the cursor on a real species."""
        stages = self.stages
        if not stages:
            return
        self.evo_stage = max(0, min(len(stages) - 1, stage))
        self.evo_row = max(0, min(len(stages[self.evo_stage]) - 1, row))

    def open_species(self, species_id, return_to=None):
        """Show a species' entry; False if it isn't on the SD card.

        return_to sets where B goes from there (otherwise it is unchanged, so
        hopping through an evolution chain still leads back to the same place).
        """
        pos = self.dex.position(species_id)
        if pos is None:
            return False
        if return_to is not None:
            self.detail_return = return_to
        if pos not in self.visible:  # hidden by a filter: show everything
            if self.browse:
                self.browse.clear()
            self.set_filter(None, 0)
        self.index = self.visible.index(pos)
        self._show_entry()
        return True

    def _show_entry(self):
        """Show the selected entry, always starting on its INFO tab."""
        self.view = DETAIL
        self.tab = INFO
        self.move_scroll = 0

    def _step(self, delta):
        """Move by one entry, wrapping from the end back to the start."""
        if self.visible:
            self.index = (self.index + delta) % len(self.visible)
            self.tab = INFO
            self.move_scroll = 0

    def _jump(self, delta):
        """Move by a page, stopping at either end."""
        if self.visible:
            self.index = max(0, min(len(self.visible) - 1, self.index + delta))
            self.tab = INFO
            self.move_scroll = 0

    def cycle_filter(self, step=1):
        """All -> first type -> ... -> last type -> All, or backwards with step=-1."""
        options = [None] + self.available_types
        self.set_filter(options[(options.index(self.type_filter) + step) % len(options)])

    def cycle_region(self, step=1):
        """All regions -> Kanto -> ... -> Paldea -> All."""
        options = [0] + self.available_regions
        self.set_filter(
            self.type_filter, options[(options.index(self.region_filter) + step) % len(options)]
        )

    @property
    def region_name(self):
        return REGIONS[self.region_filter]

    def set_filter(self, type_name, region=None):
        """Show one type (None for all) and, if given, one region (0 for all)."""
        current = self.selected
        self.type_filter = type_name
        if region is not None:
            self.region_filter = region
        dex = self.dex
        picks = self.browse.positions if self.browse else None
        self.visible = [
            p
            for p in range(len(dex))
            if (type_name is None or dex.has_type(p, type_name))
            and (not self.region_filter or dex.region(p) == self.region_filter)
            and (picks is None or p in picks)
        ]
        # Keep the same Pokémon selected when it survives the filter.
        self.index = self.visible.index(current) if current in self.visible else 0


def audio_due(before, state):
    """Play when an entry opens or changes, not when coming back to the same one.

    before is (view, selected Pokémon ID) from before the button was handled.
    """
    view, pokemon_id = before
    if state.view != DETAIL or state.selected_id is None:
        return False
    return view in (LIST, SEARCH) or state.selected_id != pokemon_id
