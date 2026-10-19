"""Navigation state, independent of pygame so it can be tested headless."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto

from pokedex.models import EvolutionChain, Pokemon
from pokedex.search import search
from pokedex.ui import keyboard
from pokedex.ui.settings import ROWS as SETTING_ROWS
from pokedex.ui.settings import Settings
from pokedex.ui.theme import TYPE_ORDER


class Action(Enum):
    """The physical buttons: a D-pad plus A, B, SELECT and START."""

    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    A = auto()
    B = auto()
    SELECT = auto()
    START = auto()
    """Opens the scanner from any screen; scans when already there."""


class View(Enum):
    HOME = auto()
    LIST = auto()
    DETAIL = auto()
    EVOLUTION = auto()
    SEARCH = auto()
    SCANNER = auto()
    SETTINGS = auto()


# Home screen entries, top to bottom, and the screen each opens.
MENU: tuple[tuple[str, View], ...] = (
    ("POKÉDEX", View.LIST),
    ("SEARCH", View.SEARCH),
    ("SCANNER", View.SCANNER),
    ("SETTINGS", View.SETTINGS),
)

MAX_QUERY = 12


class ScanPhase(Enum):
    LIVE = auto()
    """Camera preview, waiting for A."""
    REQUESTED = auto()
    """A was pressed; the app captures a frame and starts recognition."""
    SCANNING = auto()
    CHOOSE = auto()
    """Not sure enough: pick from the top guesses."""


@dataclass(frozen=True)
class ScanResult:
    pokemon_id: int
    confidence: float
    from_card: bool = False


@dataclass
class ScannerState:
    phase: ScanPhase = ScanPhase.LIVE
    choices: list[ScanResult] = field(default_factory=list)
    choice: int = 0
    message: str = ""
    """Shown under the preview, e.g. when nothing was recognised."""


@dataclass
class SearchState:
    """The search screen: a query typed on the on-screen keyboard and its results.

    The cursor is either on the keyboard or, after OK, in the results list.
    """

    pokemon: Sequence[Pokemon]
    query: str = ""
    results: list[Pokemon] = field(default_factory=list)
    in_results: bool = False
    key_row: int = 0
    key_index: int = 0
    result_index: int = 0

    @property
    def key(self) -> keyboard.Key:
        return keyboard.LAYOUT[self.key_row][self.key_index]

    @property
    def selected(self) -> Pokemon | None:
        return self.results[self.result_index] if self.results else None

    def set_query(self, query: str) -> None:
        self.query = query[:MAX_QUERY]
        self.results = search(self.pokemon, self.query)
        self.result_index = 0
        if not self.results:
            self.in_results = False

    def type(self, text: str) -> None:
        self.set_query(self.query + text)

    def backspace(self) -> bool:
        """Delete the last character; False if there was nothing to delete."""
        if not self.query:
            return False
        self.set_query(self.query[:-1])
        return True

    def press(self, row: int, index: int) -> None:
        """Press an on-screen key (also moves the cursor there, for touch)."""
        self.key_row, self.key_index = row, index
        match self.key.value:
            case keyboard.DELETE:
                self.backspace()
            case keyboard.DONE:
                self.in_results = bool(self.results)
            case value:
                self.type(value)

    def move_key(self, d_row: int, d_col: int) -> None:
        self.key_row, self.key_index = keyboard.move(self.key_row, self.key_index, d_row, d_col)

    def move_result(self, delta: int) -> None:
        if self.results:
            self.result_index = (self.result_index + delta) % len(self.results)


@dataclass
class PokedexState:
    pokemon: Sequence[Pokemon]
    chains: Mapping[int, EvolutionChain] = field(default_factory=dict)
    page_size: int = 8
    """How far LEFT/RIGHT jump in the list; the renderer sets it to the visible rows."""
    settings: Settings = field(default_factory=Settings)
    view: View = View.HOME
    menu_index: int = 0
    """Home screen selection; kept so the menu remembers the last choice."""
    settings_index: int = 0
    pending_action: str | None = None
    """A Shut down / Restart row pressed once; a second A confirms it."""
    power_request: str | None = None
    """A confirmed Shut down / Restart for the app to carry out."""
    notice: str = ""
    """A message under the settings list, e.g. why shut down didn't happen."""
    detail_return: View = View.LIST
    """Where B goes from an entry: the list, or the search it was opened from."""
    type_filter: str | None = None
    index: int = 0
    """Position of the selection within visible."""
    evo_stage: int = 0
    evo_row: int = 0
    """Evolution screen cursor: column (stage) and row within it."""
    visible: list[Pokemon] = field(init=False)
    available_types: list[str] = field(init=False)
    by_id: dict[int, Pokemon] = field(init=False)
    search: SearchState = field(init=False)
    scanner: ScannerState = field(default_factory=ScannerState)

    def __post_init__(self) -> None:
        self.visible = list(self.pokemon)
        self.search = SearchState(self.pokemon)
        self.by_id = {p.id: p for p in self.pokemon}
        present = {t for p in self.pokemon for t in p.types}
        self.available_types = [t for t in TYPE_ORDER if t in present]
        self.available_types += sorted(present - set(TYPE_ORDER))

    @property
    def selected(self) -> Pokemon | None:
        return self.visible[self.index] if self.visible else None

    @property
    def chain(self) -> EvolutionChain | None:
        """The selected Pokémon's evolution chain, if it has been fetched."""
        mon = self.selected
        if mon is None or mon.evolution_chain_id is None:
            return None
        return self.chains.get(mon.evolution_chain_id)

    @property
    def stages(self) -> list[list[int]]:
        return self.chain.stages() if self.chain else []

    @property
    def evo_cursor(self) -> int | None:
        """Species ID under the evolution screen cursor."""
        stages = self.stages
        return stages[self.evo_stage][self.evo_row] if stages else None

    def handle(self, action: Action) -> None:
        if action is Action.START and self.view is not View.SCANNER:
            self.open_scanner()
            return
        match self.view:
            case View.HOME:
                self._handle_home(action)
            case View.SCANNER:
                self._handle_scanner(action)
            case View.SETTINGS:
                self._handle_settings(action)
            case View.SEARCH:
                self._handle_search(action)
            case View.LIST:
                self._handle_list(action)
            case View.DETAIL:
                self._handle_detail(action)
            case View.EVOLUTION:
                self._handle_evolution(action)

    def _handle_list(self, action: Action) -> None:
        match action:
            case Action.UP:
                self._step(-1)
            case Action.DOWN:
                self._step(1)
            case Action.LEFT:
                self._jump(-self.page_size)
            case Action.RIGHT:
                self._jump(self.page_size)
            case Action.A if self.selected:
                self.view = View.DETAIL
                self.detail_return = View.LIST
            case Action.B if self.type_filter:
                self.set_filter(None)
            case Action.B:
                self.view = View.HOME
            case Action.SELECT:
                self.cycle_filter()

    def _handle_home(self, action: Action) -> None:
        match action:
            case Action.UP:
                self.menu_index = (self.menu_index - 1) % len(MENU)
            case Action.DOWN:
                self.menu_index = (self.menu_index + 1) % len(MENU)
            case Action.A:
                self.open_menu(self.menu_index)

    def open_menu(self, index: int) -> None:
        self.menu_index = index
        self.view = MENU[index][1]
        self.settings_index = 0

    def _handle_settings(self, action: Action) -> None:
        row = SETTING_ROWS[self.settings_index]
        match action:
            case Action.UP | Action.DOWN:
                step = -1 if action is Action.UP else 1
                self.settings_index = (self.settings_index + step) % len(SETTING_ROWS)
                self.pending_action = None
            case Action.LEFT | Action.RIGHT if row.kind != "action":
                self.change_setting(self.settings_index, -1 if action is Action.LEFT else 1)
            case Action.A if row.kind != "slider":
                self.change_setting(self.settings_index, 1)
            case Action.B if self.pending_action:
                self.pending_action = None
            case Action.B:
                self.view = View.HOME
                self.notice = ""

    def change_setting(self, row: int, delta: int) -> None:
        """Change a setting, or press an action row (the second press confirms it)."""
        self.settings_index = row
        target = SETTING_ROWS[row]
        if target.kind == "action":
            if self.pending_action == target.key:
                self.power_request, self.pending_action = target.key, None
            else:
                self.pending_action = target.key
            return
        self.pending_action = None
        self.settings = self.settings.adjusted(target.key, delta)

    def _handle_search(self, action: Action) -> None:
        s = self.search
        if s.in_results:
            match action:
                case Action.UP:
                    s.move_result(-1)
                case Action.DOWN:
                    s.move_result(1)
                case Action.A if s.selected:
                    self.open_species(s.selected.id, return_to=View.SEARCH)
                case Action.B | Action.LEFT | Action.SELECT:
                    s.in_results = False
            return
        match action:
            case Action.UP:
                s.move_key(-1, 0)
            case Action.DOWN:
                s.move_key(1, 0)
            case Action.LEFT:
                s.move_key(0, -1)
            case Action.RIGHT:
                s.move_key(0, 1)
            case Action.A:
                s.press(s.key_row, s.key_index)
            case Action.B if not s.backspace():
                self.view = View.HOME
            case Action.SELECT:
                s.in_results = bool(s.results)

    def open_scanner(self) -> None:
        self.view = View.SCANNER
        self.scanner = ScannerState()

    def _handle_scanner(self, action: Action) -> None:
        scan = self.scanner
        match scan.phase, action:
            case ScanPhase.LIVE, Action.A | Action.START:
                scan.phase = ScanPhase.REQUESTED
                scan.message = ""
            case ScanPhase.LIVE, Action.B:
                self.view = View.HOME
            case ScanPhase.REQUESTED | ScanPhase.SCANNING, Action.B:
                scan.phase = ScanPhase.LIVE  # the result is ignored when it arrives
            case ScanPhase.CHOOSE, Action.UP:
                scan.choice = (scan.choice - 1) % len(scan.choices)
            case ScanPhase.CHOOSE, Action.DOWN:
                scan.choice = (scan.choice + 1) % len(scan.choices)
            case ScanPhase.CHOOSE, Action.A:
                self.choose_scan_result(scan.choice)
            case ScanPhase.CHOOSE, Action.B:
                scan.phase = ScanPhase.LIVE

    def scan_started(self) -> None:
        self.scanner.phase = ScanPhase.SCANNING

    def scan_failed(self, message: str) -> None:
        self.scanner.phase = ScanPhase.LIVE
        self.scanner.message = message

    def scan_finished(self, results: Sequence[ScanResult]) -> None:
        """Open the entry if sure, else offer the top guesses; ignored if cancelled."""
        scan = self.scanner
        if self.view is not View.SCANNER or scan.phase is not ScanPhase.SCANNING:
            return
        known = [r for r in results if r.pokemon_id in self.by_id]
        if not known:
            self.scan_failed("Couldn't recognise that. Try again, closer or in better light.")
            return
        best = known[0]
        if best.from_card or best.confidence >= self.settings.auto_open_confidence:
            scan.phase = ScanPhase.LIVE
            self.open_species(best.pokemon_id, return_to=View.SCANNER)
        else:
            scan.phase, scan.choices, scan.choice = ScanPhase.CHOOSE, known, 0

    def choose_scan_result(self, index: int) -> None:
        scan = self.scanner
        if 0 <= index < len(scan.choices):
            scan.phase = ScanPhase.LIVE
            self.open_species(scan.choices[index].pokemon_id, return_to=View.SCANNER)

    def type_text(self, text: str) -> None:
        """Typing on a real keyboard: letters and digits go into the search.

        The cursor jumps to OK so Enter then moves into the results.
        """
        if self.view is not View.SEARCH or self.search.in_results:
            return
        typed = "".join(c for c in text.lower() if c.isascii() and c.isalnum())
        if typed:
            self.search.type(typed)
            self.search.key_row, self.search.key_index = keyboard.DONE_POSITION

    def _handle_detail(self, action: Action) -> None:
        match action:
            case Action.UP | Action.LEFT:
                self._step(-1)
            case Action.DOWN | Action.RIGHT:
                self._step(1)
            case Action.A:
                self.open_evolution()
            case Action.B:
                self.view = self.detail_return

    def _handle_evolution(self, action: Action) -> None:
        match action:
            case Action.UP:
                self.move_evo_cursor(self.evo_stage, self.evo_row - 1)
            case Action.DOWN:
                self.move_evo_cursor(self.evo_stage, self.evo_row + 1)
            case Action.LEFT:
                self.move_evo_cursor(self.evo_stage - 1, self.evo_row)
            case Action.RIGHT:
                self.move_evo_cursor(self.evo_stage + 1, self.evo_row)
            case Action.A if self.evo_cursor is not None:
                self.open_species(self.evo_cursor)
            case Action.B:
                self.view = View.DETAIL

    def open_evolution(self) -> None:
        """Show the selected Pokémon's chain with the cursor on it."""
        mon = self.selected
        if mon is None:
            return
        self.view = View.EVOLUTION
        self.evo_stage = self.evo_row = 0
        for stage, species_ids in enumerate(self.stages):
            if mon.id in species_ids:
                self.evo_stage, self.evo_row = stage, species_ids.index(mon.id)

    def move_evo_cursor(self, stage: int, row: int) -> None:
        """Move within the chain, keeping the cursor on a real species."""
        stages = self.stages
        if not stages:
            return
        self.evo_stage = max(0, min(len(stages) - 1, stage))
        self.evo_row = max(0, min(len(stages[self.evo_stage]) - 1, row))

    def open_species(self, species_id: int, *, return_to: View | None = None) -> bool:
        """Show a species' detail screen; False if it is not in the database.

        return_to sets where B goes from there (otherwise it is unchanged, so
        hopping through an evolution chain still leads back to the same place).
        """
        mon = self.by_id.get(species_id)
        if mon is None:
            return False
        if return_to is not None:
            self.detail_return = return_to
        if mon not in self.visible:
            self.set_filter(None)
        self.index = self.visible.index(mon)
        self.view = View.DETAIL
        return True

    def _step(self, delta: int) -> None:
        """Move by one entry, wrapping from the end back to the start."""
        if self.visible:
            self.index = (self.index + delta) % len(self.visible)

    def _jump(self, delta: int) -> None:
        """Move by a page, stopping at either end."""
        if self.visible:
            self.index = max(0, min(len(self.visible) - 1, self.index + delta))

    def select_index(self, index: int) -> None:
        if 0 <= index < len(self.visible):
            self.index = index

    def cycle_filter(self) -> None:
        """All -> first type -> ... -> last type -> All."""
        options: list[str | None] = [None, *self.available_types]
        self.set_filter(options[(options.index(self.type_filter) + 1) % len(options)])

    def set_filter(self, type_name: str | None) -> None:
        current = self.selected
        self.type_filter = type_name
        self.visible = [p for p in self.pokemon if type_name is None or type_name in p.types]
        # Keep the same Pokémon selected when it survives the filter.
        self.index = next((i for i, p in enumerate(self.visible) if p == current), 0)
