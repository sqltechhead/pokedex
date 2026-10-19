"""Drawing the home, list, detail, evolution, scanner and settings screens.

Layouts are designed at 480x320 and scaled by ``s`` to the actual screen, so
the same code fits a 3.5" 480x320 panel or a 7" 800x480 one.
"""

from typing import Literal

import pygame

from pokedex.models import EvolutionChain, Pokemon
from pokedex.ui import keyboard
from pokedex.ui.assets import ImageCache
from pokedex.ui.settings import ROWS as SETTING_ROWS
from pokedex.ui.state import MENU, PokedexState, ScanPhase, View
from pokedex.ui.theme import STAT_LABELS, Color, Theme
from pokedex.units import Units, format_height, format_weight

Anchor = Literal["topleft", "midleft", "center", "midright", "topright", "midbottom"]

DESIGN_SIZE = (480, 320)
STAT_BAR_MAX = 200  # base stats above this fill the whole bar
COMPACT_CELL_HEIGHT = 60  # evolution cells shorter than this become one-line rows


class Renderer:
    def __init__(
        self, screen: pygame.Surface, images: ImageCache, theme: Theme | None = None
    ) -> None:
        self.screen = screen
        self.images = images
        self.theme = theme or Theme()
        self.w, self.h = screen.get_size()
        self.s = min(self.w / DESIGN_SIZE[0], self.h / DESIGN_SIZE[1])
        self.font_title = self._font(self.theme.font_bold, 18)
        self.font_name = self._font(self.theme.font_bold, 16)
        self.font_body = self._font(self.theme.font_regular, 13)
        self.font_bold = self._font(self.theme.font_bold, 12)
        self.font_small = self._font(self.theme.font_regular, 11)
        self.font_tiny = self._font(self.theme.font_bold, 9)
        # Touch targets from the last frame, used by the app for hit testing.
        self.row_hits: list[tuple[pygame.Rect, int]] = []
        self.evo_hits: list[tuple[pygame.Rect, tuple[int, int]]] = []
        self.menu_hits: list[tuple[pygame.Rect, int]] = []
        self.settings_hits: list[tuple[pygame.Rect, int]] = []
        self.key_hits: list[tuple[pygame.Rect, tuple[int, int]]] = []
        self.result_hits: list[tuple[pygame.Rect, int]] = []
        self.choice_hits: list[tuple[pygame.Rect, int]] = []
        self.preview_hit = pygame.Rect(0, 0, 0, 0)
        # Scanner screen inputs, set by the app each frame.
        self.preview = None
        """The camera frame to show (a PIL image), or None."""
        self.frozen = None
        """The frame being recognised, held on screen while scanning."""
        self.camera_problem: str | None = None
        self.scanner_note = ""
        self.filter_hit = pygame.Rect(0, 0, 0, 0)

    def _font(self, path: object, size: int) -> pygame.font.Font:
        return pygame.font.Font(path, self.px(size))

    def px(self, value: float) -> int:
        return round(value * self.s)

    # Layout regions shared by both screens.
    @property
    def header(self) -> pygame.Rect:
        return pygame.Rect(0, 0, self.w, self.px(30))

    @property
    def footer(self) -> pygame.Rect:
        height = self.px(18)
        return pygame.Rect(0, self.h - height, self.w, height)

    @property
    def body(self) -> pygame.Rect:
        pad = self.px(8)
        top = self.header.bottom + pad
        return pygame.Rect(pad, top, self.w - 2 * pad, self.footer.top - pad - top)

    @property
    def row_height(self) -> int:
        return self.px(26)

    @property
    def list_rows(self) -> int:
        return max(1, self.body.height // self.row_height)

    def draw(self, state: PokedexState) -> None:
        self.screen.fill(self.theme.bg)
        self.row_hits = []
        self.evo_hits = []
        self.menu_hits = []
        self.key_hits = []
        self.result_hits = []
        self.choice_hits = []
        self.settings_hits = []
        match state.view:
            case View.HOME:
                self._draw_home(state)
            case View.SCANNER:
                self._draw_scanner(state)
            case View.SETTINGS:
                self._draw_settings(state)
            case View.SEARCH:
                self._draw_search(state)
            case _ if not state.pokemon:
                self._draw_empty()
            case View.LIST:
                self._draw_list(state)
            case View.DETAIL:
                self._draw_detail(state)
            case View.EVOLUTION:
                self._draw_evolution(state)

    # Screens

    def _draw_empty(self) -> None:
        self._header_bar("POKÉDEX")
        center = self.screen.get_rect().center
        self.text("No Pokémon yet.", self.font_name, self.theme.text, center, "center")
        hint = "Run:  uv run pokedex-fetch"
        below = (center[0], center[1] + self.px(24))
        self.text(hint, self.font_body, self.theme.muted, below, "center")

    def _draw_home(self, state: PokedexState) -> None:
        theme = self.theme
        self._header_bar("POKÉDEX")
        body = self.body
        gap = self.px(8)
        row_h = min(self.px(64), (body.height - gap * (len(MENU) - 1)) // len(MENU))
        top = body.centery - (row_h * len(MENU) + gap * (len(MENU) - 1)) // 2
        settings = state.settings
        subtitles = {
            View.LIST: f"{len(state.pokemon)} entries",
            View.SEARCH: "Find by name or number",
            View.SCANNER: "Point at a plush or card",
            View.SETTINGS: (
                f"Volume {settings.describe('volume')} · Sound {settings.describe('sound')}"
            ),
        }
        for index, (title, view) in enumerate(MENU):
            rect = pygame.Rect(body.left, top + index * (row_h + gap), body.width, row_h)
            selected = index == state.menu_index
            pygame.draw.rect(
                self.screen, theme.accent if selected else theme.panel, rect,
                border_radius=self.px(8),
            )  # fmt: skip
            ink = theme.text if selected else theme.muted
            icon_center = (rect.left + rect.height // 2 + self.px(6), rect.centery)
            self._menu_icon(view, icon_center, round(rect.height * 0.24), ink)
            x = rect.left + rect.height + self.px(12)
            self.text(title, self.font_name, theme.text, (x, rect.centery - self.px(8)), "midleft")
            subtitle = (x, rect.centery + self.px(11))
            self.text(subtitles[view], self.font_small, ink, subtitle, "midleft")
            self.menu_hits.append((rect, index))
        self._footer_hints(["▲▼ choose", "A open"])

    def _menu_icon(self, view: View, center: tuple[int, int], r: int, color: Color) -> None:
        """Simple line icons: a Poké Ball, a magnifier, a viewfinder and sliders."""
        x, y = center
        width = max(2, self.px(2))
        if view is View.LIST:
            pygame.draw.circle(self.screen, color, center, r, width)
            pygame.draw.line(self.screen, color, (x - r, y), (x + r, y), width)
            pygame.draw.circle(self.screen, color, center, max(3, r // 3))
        elif view is View.SEARCH:
            lens = round(r * 0.62)
            lens_center = (x - round(r * 0.25), y - round(r * 0.25))
            pygame.draw.circle(self.screen, color, lens_center, lens, width)
            handle = round(lens * 0.71)
            start = (lens_center[0] + handle, lens_center[1] + handle)
            pygame.draw.line(self.screen, color, start, (x + r, y + r), width + 1)
        elif view is View.SCANNER:
            arm = r // 2
            for dx in (-1, 1):
                for dy in (-1, 1):
                    corner = (x + dx * r, y + dy * r)
                    pygame.draw.line(
                        self.screen, color, corner, (corner[0] - dx * arm, corner[1]), width
                    )
                    pygame.draw.line(
                        self.screen, color, corner, (corner[0], corner[1] - dy * arm), width
                    )
            pygame.draw.circle(self.screen, color, center, max(3, r // 3))
        else:
            for i, knob in zip((-1, 0, 1), (0.3, -0.4, 0.1), strict=True):
                line_y = y + i * round(r * 0.7)
                pygame.draw.line(self.screen, color, (x - r, line_y), (x + r, line_y), width)
                pygame.draw.circle(
                    self.screen, color, (x + round(knob * r * 2), line_y), max(3, r // 4)
                )

    def _draw_search(self, state: PokedexState) -> None:
        theme = self.theme
        search = state.search
        self._header_bar("SEARCH")
        body = self.body
        gap = self.px(6)

        # Query field
        field = pygame.Rect(body.left, body.top, body.width, self.px(28))
        pygame.draw.rect(self.screen, theme.panel_light, field, border_radius=self.px(6))
        icon = (field.left + self.px(14), field.centery)
        self._menu_icon(View.SEARCH, icon, self.px(7), theme.muted)
        text_x = field.left + self.px(28)
        if search.query:
            shown = self.text(search.query.upper(), self.font_name, theme.text,
                              (text_x, field.centery), "midleft")  # fmt: skip
            if not search.in_results:  # caret
                caret = pygame.Rect(shown.right + self.px(2), 0, self.px(2), self.px(16))
                caret.centery = field.centery
                pygame.draw.rect(self.screen, theme.accent, caret)
        else:
            self.text("Name or number", self.font_body, theme.muted,
                      (text_x, field.centery), "midleft")  # fmt: skip

        top = field.bottom + gap * 2
        pad = self.px(3)
        board = pygame.Rect(body.left, top, round(body.width * 0.6), body.bottom - top)
        key_w = (board.width - pad * (keyboard.COLUMNS - 1)) / keyboard.COLUMNS
        rows = len(keyboard.LAYOUT)
        key_h = min(self.px(38), (board.height - pad * (rows - 1)) // rows)
        for row, keys in enumerate(keyboard.LAYOUT):
            for index, key in enumerate(keys):
                column = keyboard.column_of(row, index)
                rect = pygame.Rect(
                    round(board.left + column * (key_w + pad)),
                    board.top + row * (key_h + pad),
                    round(key.span * key_w + (key.span - 1) * pad),
                    key_h,
                )
                cursor = (row, index) == (search.key_row, search.key_index)
                fill = theme.accent if cursor and not search.in_results else theme.panel
                pygame.draw.rect(self.screen, fill, rect, border_radius=self.px(4))
                if cursor and search.in_results:
                    pygame.draw.rect(self.screen, theme.muted, rect, width=1,
                                     border_radius=self.px(4))  # fmt: skip
                font = self.font_bold if key.span == 1 else self.font_tiny
                self.text(key.label, font, theme.text, rect.center, "center")
                self.key_hits.append((rect, (row, index)))

        results = pygame.Rect(board.right + gap * 2, top, body.right - board.right - gap * 2,
                              body.bottom - top)  # fmt: skip
        self._search_results(state, results)

        if search.in_results:
            self._footer_hints(["▲▼ choose", "A open", "B keyboard"])
        else:
            hints = ["▲▼◀▶ keys", "A type", "B delete"]
            self._footer_hints([*hints, "SEL results" if search.results else ""])

    def _search_results(self, state: PokedexState, area: pygame.Rect) -> None:
        theme = self.theme
        search = state.search
        if not search.query:
            message = "Type to search"
        elif not search.results:
            message = "No matches"
        else:
            count = len(search.results)
            message = f"{count} found" if count != 1 else "1 found"
        self.text(
            message, self.font_small, theme.muted, (area.left + self.px(4), area.top), "topleft"
        )

        row_h = self.px(24)
        list_top = area.top + self.px(18)
        rows = max(1, (area.bottom - list_top) // row_h)
        total = len(search.results)
        first = max(0, min(search.result_index - rows // 2, total - rows))
        for row, index in enumerate(range(first, min(first + rows, total))):
            mon = search.results[index]
            rect = pygame.Rect(area.left, list_top + row * row_h, area.width, row_h - self.px(2))
            if search.in_results and index == search.result_index:
                pygame.draw.rect(self.screen, theme.accent, rect, border_radius=self.px(4))
            number = self.text(f"{mon.id:03d}", self.font_tiny, theme.muted,
                               (rect.left + self.px(4), rect.centery), "midleft")  # fmt: skip
            icon_center = (number.right + self.px(4) + rect.height // 2, rect.centery)
            if image := self.images.get(mon.sprite_path, rect.height + self.px(6)):
                self.screen.blit(image, image.get_rect(center=icon_center))
            name_x = icon_center[0] + rect.height // 2 + self.px(3)
            name = ellipsize(mon.name, self.font_body, rect.right - name_x - self.px(2))
            self.text(name, self.font_body, theme.text, (name_x, rect.centery), "midleft")
            self.result_hits.append((rect, index))

    def _draw_scanner(self, state: PokedexState) -> None:
        theme = self.theme
        scan = state.scanner
        self._header_bar("SCANNER")
        body = self.body
        side = body.height
        preview = pygame.Rect(body.left, body.top, side, side)
        self.preview_hit = preview
        self._camera_view(preview, scanning=scan.phase is ScanPhase.SCANNING)

        panel = pygame.Rect(preview.right + self.px(12), body.top, 0, body.height)
        panel.width = body.right - panel.left
        if scan.phase is ScanPhase.CHOOSE:
            self._scan_choices(state, panel)
            self._footer_hints(["▲▼ choose", "A open", "B try again"])
            return
        if scan.phase in (ScanPhase.REQUESTED, ScanPhase.SCANNING):
            dots = "." * (1 + pygame.time.get_ticks() // 400 % 3)
            self.text(f"Scanning{dots}", self.font_name, theme.text, panel.topleft, "topleft")
            self._footer_hints(["B cancel"])
            return

        self.text("Point at a Pokémon", self.font_name, theme.text, panel.topleft, "topleft")
        tip = pygame.Rect(panel.left, panel.top + self.px(26), panel.width, self.px(64))
        self.paragraph(
            "Hold a plush, figure or card inside the frame, then press A.",
            self.font_body, theme.muted, tip,
        )  # fmt: skip
        notes = [(scan.message, theme.accent), (self.scanner_note, theme.muted)]
        top = tip.bottom + self.px(8)
        for note, color in notes:
            if note:
                box = pygame.Rect(panel.left, top, panel.width, panel.bottom - top)
                self.paragraph(note, self.font_small, color, box)
                lines = len(wrap(note, self.font_small, panel.width))
                top += lines * self.font_small.get_linesize() + self.px(8)
        self._footer_hints(["A scan", "B back"])

    def _camera_view(self, rect: pygame.Rect, *, scanning: bool) -> None:
        theme = self.theme
        pygame.draw.rect(self.screen, theme.panel, rect, border_radius=self.px(8))
        if self.preview is not None:
            from pokedex.camera import square_crop

            frame = square_crop(self.preview)
            surface = pygame.image.frombytes(frame.tobytes(), frame.size, "RGB")
            self.screen.blit(pygame.transform.smoothscale(surface, rect.size), rect)
        else:
            message = self.camera_problem or "Starting camera…"
            box = rect.inflate(-self.px(24), -self.px(24))
            self.paragraph(message, self.font_small, theme.muted, box)

        if scanning:
            shade = pygame.Surface(rect.size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, 90))
            self.screen.blit(shade, rect)
            travel = rect.height - self.px(8)
            y = rect.top + self.px(4) + (pygame.time.get_ticks() // 4) % travel
            glow = pygame.Surface((rect.width, self.px(14)), pygame.SRCALPHA)
            for i in range(glow.get_height()):
                alpha = 150 - abs(i - glow.get_height() // 2) * 20
                pygame.draw.line(glow, (*theme.accent, max(0, alpha)), (0, i), (rect.width, i))
            self.screen.blit(glow, (rect.left, y - glow.get_height() // 2))

        # Corner guides: the square the scanner looks at.
        inset, arm, width = self.px(10), self.px(22), max(2, self.px(3))
        color = theme.accent
        for cx, dx in ((rect.left + inset, 1), (rect.right - inset, -1)):
            for cy, dy in ((rect.top + inset, 1), (rect.bottom - inset, -1)):
                pygame.draw.line(self.screen, color, (cx, cy), (cx + dx * arm, cy), width)
                pygame.draw.line(self.screen, color, (cx, cy), (cx, cy + dy * arm), width)

    def _scan_choices(self, state: PokedexState, panel: pygame.Rect) -> None:
        theme = self.theme
        scan = state.scanner
        self.text("Is it…?", self.font_name, theme.text, panel.topleft, "topleft")
        row_h = self.px(52)
        top = panel.top + self.px(28)
        for index, result in enumerate(scan.choices[:3]):
            mon = state.by_id[result.pokemon_id]
            rect = pygame.Rect(panel.left, top + index * (row_h + self.px(4)), panel.width, row_h)
            selected = index == scan.choice
            pygame.draw.rect(
                self.screen, theme.accent if selected else theme.panel, rect,
                border_radius=self.px(6),
            )  # fmt: skip
            icon_center = (rect.left + rect.height // 2, rect.centery)
            if image := self.images.get(mon.sprite_path, rect.height):
                self.screen.blit(image, image.get_rect(center=icon_center))
            x = rect.left + rect.height + self.px(2)
            name = ellipsize(mon.name, self.font_bold, rect.right - x - self.px(6))
            self.text(name, self.font_bold, theme.text, (x, rect.centery - self.px(8)), "midleft")
            bar = pygame.Rect(
                x, rect.centery + self.px(6), rect.right - x - self.px(44), self.px(6)
            )
            track = theme.bg if selected else theme.panel_light
            pygame.draw.rect(self.screen, track, bar, border_radius=bar.height // 2)
            fill = bar.copy()
            fill.width = max(bar.height, round(bar.width * result.confidence))
            pygame.draw.rect(self.screen, theme.text, fill, border_radius=bar.height // 2)
            percent = f"{result.confidence:.0%}"
            self.text(percent, self.font_tiny, theme.text,
                      (rect.right - self.px(6), bar.centery), "midright")  # fmt: skip
            self.choice_hits.append((rect, index))

    def _draw_settings(self, state: PokedexState) -> None:
        theme = self.theme
        self._header_bar("SETTINGS")
        body = self.body.copy()
        if state.notice:
            notice_h = self.font_small.get_linesize() * 2 + self.px(6)
            notice = pygame.Rect(body.left, body.bottom - notice_h, body.width, notice_h)
            self.paragraph(state.notice, self.font_small, theme.accent, notice)
            body.height -= notice_h
        row_h = self.px(36)
        shown = max(1, body.height // row_h)
        total = len(SETTING_ROWS)
        first = max(0, min(state.settings_index - shown // 2, total - shown))
        for slot, index in enumerate(range(first, min(first + shown, total))):
            row = SETTING_ROWS[index]
            rect = pygame.Rect(
                body.left, body.top + slot * row_h, body.width - self.px(8), row_h - self.px(4)
            )
            self._settings_row(state, row, rect, selected=index == state.settings_index)
            self.settings_hits.append((rect, index))
        if total > shown:
            track = pygame.Rect(body.right - self.px(3), body.top, self.px(3), shown * row_h)
            self._scrollbar(track, first, shown, total)
        row = SETTING_ROWS[state.settings_index]
        verb = {"slider": "", "switch": "A switch", "choice": "A change", "action": "A select"}
        change = "◀▶ change" if row.kind != "action" else ""
        self._footer_hints(["▲▼ choose", change, verb[row.kind], "B back"])

    def _settings_row(self, state: PokedexState, row, rect: pygame.Rect, *, selected: bool) -> None:
        theme = self.theme
        settings = state.settings
        fill = theme.accent if selected else theme.panel
        pygame.draw.rect(self.screen, fill, rect, border_radius=self.px(6))
        self.text(row.label, self.font_body, theme.text,
                  (rect.left + self.px(12), rect.centery), "midleft")  # fmt: skip
        right = (rect.right - self.px(12), rect.centery)
        if row.kind == "slider":
            bar = pygame.Rect(0, 0, self.px(110), self.px(8))
            bar.midright = (right[0] - self.px(44), rect.centery)
            track = theme.bg if selected else theme.panel_light
            pygame.draw.rect(self.screen, track, bar, border_radius=bar.height // 2)
            filled = bar.copy()
            filled.width = max(bar.height, round(bar.width * settings.volume))
            pygame.draw.rect(self.screen, theme.text, filled, border_radius=bar.height // 2)
            self.text(settings.describe(row.key), self.font_bold, theme.text, right, "midright")
        elif row.kind == "switch":
            on = getattr(settings, row.key)
            self._switch(right, on, selected)
            color = theme.text if on or selected else theme.muted
            label = (right[0] - self.px(44), rect.centery)
            self.text(settings.describe(row.key), self.font_bold, color, label, "midright")
        elif row.kind == "choice":
            value = settings.describe(row.key)
            arrows = "◀  " + value + "  ▶" if selected else value
            self.text(arrows, self.font_bold, theme.text, right, "midright")
        else:
            confirming = state.pending_action == row.key
            hint = "Press A again to confirm" if confirming else ("Press A" if selected else "")
            if hint:
                self.text(hint, self.font_small, theme.text, right, "midright")

    def draw_message(self, title: str, message: str) -> None:
        """A full-screen message, e.g. while shutting down."""
        self.screen.fill(self.theme.bg)
        self._header_bar("POKÉDEX")
        center = self.screen.get_rect().center
        self.text(title, self.font_name, self.theme.text, center, "center")
        below = (center[0], center[1] + self.px(24))
        self.text(message, self.font_body, self.theme.muted, below, "center")

    def _switch(self, midright: tuple[int, int], on: bool, selected: bool) -> None:
        theme = self.theme
        track = pygame.Rect(0, 0, self.px(34), self.px(18))
        track.midright = midright
        if on:
            color = theme.text if selected else (35, 205, 94)
        else:
            color = theme.bg if selected else theme.panel_light
        pygame.draw.rect(self.screen, color, track, border_radius=track.height // 2)
        knob_x = track.right - track.height // 2 if on else track.left + track.height // 2
        knob_color = theme.accent if on and selected else theme.text
        pygame.draw.circle(
            self.screen, knob_color, (knob_x, track.centery), track.height // 2 - self.px(3)
        )

    def _draw_list(self, state: PokedexState) -> None:
        self._header_bar("POKÉDEX")
        self._filter_label(state, self.header)

        body = self.body
        gap = self.px(8)
        preview = pygame.Rect(body.left, body.top, round(body.width * 0.4), body.height)
        rows = pygame.Rect(preview.right + gap, body.top, body.right - preview.right - gap, 0)
        rows.height = self.list_rows * self.row_height

        if selected := state.selected:
            self._preview(selected, preview)

        count = self.list_rows
        top = max(0, min(state.index - count // 2, len(state.visible) - count))
        for row, index in enumerate(range(top, min(top + count, len(state.visible)))):
            rect = pygame.Rect(
                rows.left,
                rows.top + row * self.row_height,
                rows.width - self.px(6),
                self.row_height,
            )
            self._list_row(state.visible[index], rect, selected=index == state.index)
            self.row_hits.append((rect, index))

        if len(state.visible) > count:
            self._scrollbar(
                pygame.Rect(rows.right - self.px(3), rows.top, self.px(3), rows.height),
                top,
                count,
                len(state.visible),
            )

        b_hint = "B all types" if state.type_filter else ""
        self._footer_hints(["▲▼ move", "◀▶ page", "A open", b_hint, "SEL type"])

    def _draw_detail(self, state: PokedexState) -> None:
        mon = state.selected
        assert mon is not None
        theme = self.theme
        title = self._header_bar(f"#{mon.id:03d}  {mon.name}")
        if mon.genus:
            right = (self.header.right - self.px(10), self.header.centery)
            room = right[0] - title.right - self.px(16)
            genus = ellipsize(mon.genus, self.font_body, room)
            self.text(genus, self.font_body, theme.text, right, "midright")

        body = self.body
        gap = self.px(8)
        flavor = pygame.Rect(body.left, 0, body.width, self.px(58))
        flavor.bottom = body.bottom
        top_h = flavor.top - gap - body.top

        art_size = min(round(body.width * 0.42), top_h)
        art = pygame.Rect(body.left, body.top, art_size, top_h)
        circle = min(art.width, art.height)
        pygame.draw.circle(self.screen, theme.panel, art.center, circle // 2)
        if image := self.images.get(mon.artwork_path or mon.sprite_path, circle - self.px(12)):
            self.screen.blit(image, image.get_rect(center=art.center))
        else:
            self._placeholder(art.center, circle // 3)

        info = pygame.Rect(art.right + gap * 2, body.top, body.right - art.right - gap * 2, top_h)
        self._detail_info(mon, info, state.settings.units)

        pygame.draw.rect(self.screen, theme.panel, flavor, border_radius=self.px(6))
        inner = flavor.inflate(-self.px(16), -self.px(10))
        self.paragraph(mon.flavor_text, self.font_body, theme.text, inner)

        position = f"{state.index + 1}/{len(state.visible)}"
        if not state.settings.sound:
            position = f"MUTED   {position}"
        self._footer_hints(["◀▶ prev/next", "A evolution", "B back"], right=position)

    def _draw_evolution(self, state: PokedexState) -> None:
        mon = state.selected
        assert mon is not None
        theme = self.theme
        self._header_bar(f"#{mon.id:03d}  {mon.name}")
        right = (self.header.right - self.px(10), self.header.centery)
        self.text("EVOLUTION", self.font_bold, theme.text, right, "midright")
        body = self.body

        chain = state.chain
        if chain is None:
            self.text("No evolution data yet.", self.font_name, theme.text, body.center, "center")
            below = (body.centerx, body.centery + self.px(24))
            self.text("Run:  uv run pokedex-fetch", self.font_body, theme.muted, below, "center")
            self._footer_hints(["B back"])
            return

        stages = chain.stages()
        cells = self._evolution_layout(stages, body)
        # Labels on fanned-out arrows collide, so branches show the method in the card.
        branched = {species_id for stage in stages if len(stage) > 1 for species_id in stage}
        for evolution in chain.evolutions:
            parent, child = cells[evolution.from_id], cells[evolution.to_id]
            label = "" if evolution.to_id in branched else evolution.method
            self._evolution_arrow(parent, child, label)
        for stage, species_ids in enumerate(stages):
            for row, species_id in enumerate(species_ids):
                cursor = (stage, row) == (state.evo_stage, state.evo_row)
                rect = cells[species_id]
                evolution = chain.evolution_to(species_id) if species_id in branched else None
                method = evolution.method if evolution else None
                self._evolution_cell(species_id, chain, state, rect, cursor=cursor, method=method)
                self.evo_hits.append((rect, (stage, row)))

        if len(stages) == 1:
            below = (body.centerx, cells[chain.root_id].bottom + self.px(14))
            self.text("Does not evolve.", self.font_body, theme.muted, below, "center")
        moves = "◀▶ move" if len(stages) > 1 else ""
        if any(len(stage) > 1 for stage in stages):
            moves = "▲▼◀▶ move"
        self._footer_hints([moves, "A view", "B back"])

    # Pieces

    def _evolution_layout(
        self, stages: list[list[int]], body: pygame.Rect
    ) -> dict[int, pygame.Rect]:
        """A column per stage, centred; branches stack vertically in their column."""
        n = len(stages)
        heights = [min(self.px(116), body.height // len(ids)) for ids in stages]
        # Compact columns also show each evolution method, so they need more width.
        widths = [self.px(156) if self._compact(h) else self.px(100) for h in heights]
        gap = min(self.px(130), (body.width - sum(widths)) // (n - 1)) if n > 1 else 0
        if gap < self.px(56):
            shrink = (self.px(56) - gap) * (n - 1) // n + 1
            widths = [w - shrink for w in widths]
            gap = self.px(56)
        x = body.centerx - (sum(widths) + gap * (n - 1)) // 2
        cells = {}
        for species_ids, cell_w, cell_h in zip(stages, widths, heights, strict=True):
            top = body.centery - cell_h * len(species_ids) // 2
            for row, species_id in enumerate(species_ids):
                cells[species_id] = pygame.Rect(x, top + row * cell_h, cell_w, cell_h)
            x += cell_w + gap
        return cells

    def _compact(self, cell_height: int) -> bool:
        return cell_height < self.px(COMPACT_CELL_HEIGHT)

    def _evolution_cell(
        self,
        species_id: int,
        chain: EvolutionChain,
        state: PokedexState,
        rect: pygame.Rect,
        *,
        cursor: bool,
        method: str | None,
    ) -> None:
        """A species card; method, when given, replaces the Pokédex number."""
        theme = self.theme
        mon = state.by_id.get(species_id)
        name = mon.name if mon else chain.name(species_id)
        name_color = theme.text if mon else theme.muted
        box = rect.inflate(-self.px(4), -self.px(4))
        pygame.draw.rect(self.screen, theme.panel, box, border_radius=self.px(6))
        if cursor:
            pygame.draw.rect(
                self.screen, theme.accent, box, width=self.px(2), border_radius=self.px(6)
            )

        if self._compact(rect.height):
            # One-line row for wide branches (Eevee): sprite, name, and how it evolves.
            size = box.height
            center = (box.left + size // 2 + self.px(2), box.centery)
            self._evolution_image(mon, size, center)
            x = center[0] + size // 2 + self.px(4)
            room = box.right - x - self.px(4)
            name_y = box.centery - self.px(6) if method else box.centery
            if method:
                pos = (x, name_y + self.px(12))
                self.text(
                    ellipsize(method, self.font_tiny, room),
                    self.font_tiny,
                    theme.muted,
                    pos,
                    "midleft",
                )
            label = ellipsize(name, self.font_bold, room)
            self.text(label, self.font_bold, name_color, (x, name_y), "midleft")
            return

        text_h = self.px(30)
        size = min(box.width, box.height - text_h) - self.px(6)
        image_center = (box.centerx, box.top + self.px(3) + (box.height - text_h) // 2)
        self._evolution_image(mon, size, image_center)
        subtitle_y = box.bottom - text_h + self.px(6)
        subtitle = ellipsize(method or f"#{species_id:03d}", self.font_tiny, box.width - self.px(6))
        self.text(subtitle, self.font_tiny, theme.muted, (box.centerx, subtitle_y), "center")
        label = ellipsize(name, self.font_bold, box.width - self.px(6))
        name_pos = (box.centerx, subtitle_y + self.px(13))
        self.text(label, self.font_bold, name_color, name_pos, "center")

    def _evolution_image(self, mon: Pokemon | None, size: int, center: tuple[int, int]) -> None:
        """Artwork when there is room, else the pixel sprite; '?' if not fetched."""
        image = None
        if mon:
            path = mon.artwork_path if size >= self.px(64) and mon.artwork_path else mon.sprite_path
            image = self.images.get(path, size)
        if image:
            self.screen.blit(image, image.get_rect(center=center))
        else:
            self._placeholder(center, size // 3)

    def _evolution_arrow(self, parent: pygame.Rect, child: pygame.Rect, label: str) -> None:
        theme = self.theme
        start = pygame.Vector2(parent.right - self.px(1), parent.centery)
        end = pygame.Vector2(child.left + self.px(1), child.centery)
        pygame.draw.line(self.screen, theme.muted, start, end, max(1, self.px(2)))
        direction = (end - start).normalize()
        normal = pygame.Vector2(-direction.y, direction.x)
        head = self.px(7)
        tip = end - direction * self.px(1)
        pygame.draw.polygon(
            self.screen,
            theme.muted,
            [
                tip,
                tip - direction * head + normal * head * 0.6,
                tip - direction * head - normal * head * 0.6,
            ],
        )
        if not label:
            return
        width = round(end.x - start.x) - self.px(10)
        lines = wrap(label, self.font_small, width)[:3]
        line_h = self.font_small.get_linesize()
        bottom = round(start.lerp(end, 0.5).y) - self.px(4)
        for i, line in enumerate(reversed(lines)):
            pos = (round((start.x + end.x) / 2), bottom - i * line_h)
            self.text(
                ellipsize(line, self.font_small, width),
                self.font_small,
                theme.text,
                pos,
                "midbottom",
            )

    def _header_bar(self, title: str) -> pygame.Rect:
        """Draw the red header bar; returns the title's rect."""
        header = self.header
        pygame.draw.rect(self.screen, self.theme.accent, header)
        lens = (header.left + self.px(16), header.centery)
        pygame.draw.circle(self.screen, (255, 255, 255), lens, self.px(8))
        pygame.draw.circle(self.screen, (61, 155, 224), lens, self.px(6))
        title_pos = (header.left + self.px(30), header.centery)
        return self.text(title, self.font_title, self.theme.text, title_pos, "midleft")

    def _filter_label(self, state: PokedexState, header: pygame.Rect) -> None:
        right = header.right - self.px(10)
        count = self.text(
            str(len(state.visible)),
            self.font_body,
            self.theme.text,
            (right, header.centery),
            "midright",
        )
        label = (state.type_filter or "all").upper()
        color = self.theme.type_color(state.type_filter) if state.type_filter else self.theme.panel
        badge = self.badge(label, color, (count.left - self.px(8), header.centery), "midright")
        self.filter_hit = badge.union(count).inflate(self.px(12), header.height)

    def _preview(self, mon: Pokemon, rect: pygame.Rect) -> None:
        theme = self.theme
        pygame.draw.rect(self.screen, theme.panel, rect, border_radius=self.px(8))
        text_h = self.px(58)
        art = pygame.Rect(rect.left, rect.top, rect.width, rect.height - text_h)
        size = min(art.width, art.height) - self.px(8)
        if image := self.images.get(mon.sprite_path, size):
            self.screen.blit(image, image.get_rect(center=art.center))
        else:
            self._placeholder(art.center, size // 4)

        x, y = rect.centerx, art.bottom
        self.text(f"#{mon.id:03d}", self.font_small, theme.muted, (x, y), "center")
        self.text(mon.name, self.font_name, theme.text, (x, y + self.px(16)), "center")
        self._type_badges(mon, (x, y + self.px(37)), "center")

    def _list_row(self, mon: Pokemon, rect: pygame.Rect, *, selected: bool) -> None:
        theme = self.theme
        if selected:
            pygame.draw.rect(self.screen, theme.accent, rect, border_radius=self.px(5))
        number_color = theme.text if selected else theme.muted
        x = rect.left + self.px(8)
        number = self.text(
            f"{mon.id:03d}", self.font_bold, number_color, (x, rect.centery), "midleft"
        )
        icon_box = rect.height
        icon_center = (number.right + self.px(6) + icon_box // 2, rect.centery)
        if icon := self.images.get(mon.sprite_path, icon_box + self.px(8)):
            self.screen.blit(icon, icon.get_rect(center=icon_center))
        name_x = icon_center[0] + icon_box // 2 + self.px(6)
        self.text(mon.name, self.font_body, theme.text, (name_x, rect.centery), "midleft")
        # Type dots on the right edge.
        dot_x = rect.right - self.px(10)
        for type_name in reversed(mon.types):
            center = (dot_x, rect.centery)
            if selected:
                pygame.draw.circle(self.screen, theme.text, center, self.px(5))
            pygame.draw.circle(self.screen, theme.type_color(type_name), center, self.px(4))
            dot_x -= self.px(12)

    def _detail_info(self, mon: Pokemon, rect: pygame.Rect, units: Units) -> None:
        theme = self.theme
        badges = self._type_badges(mon, (rect.left, rect.top + self.px(9)), "midleft")
        measures = f"{format_height(mon.height_dm, units)}   {format_weight(mon.weight_hg, units)}"
        self.text(
            measures,
            self.font_body,
            theme.muted,
            (badges.right + self.px(10), badges.centery),
            "midleft",
        )

        stats = mon.stats.model_dump()
        rows_top = badges.bottom + self.px(8)
        row_h = (rect.bottom - rows_top) / (len(stats) + 1)
        label_w = self.px(40)
        value_w = self.px(28)
        bar_left = rect.left + label_w + value_w
        bar_w = rect.right - bar_left
        for i, (key, value) in enumerate(stats.items()):
            cy = round(rows_top + row_h * (i + 0.5))
            self.text(STAT_LABELS[key], self.font_tiny, theme.muted, (rect.left, cy), "midleft")
            self.text(
                str(value), self.font_bold, theme.text, (bar_left - self.px(6), cy), "midright"
            )
            track = pygame.Rect(bar_left, 0, bar_w, max(4, round(row_h * 0.45)))
            track.centery = cy
            pygame.draw.rect(self.screen, theme.panel_light, track, border_radius=track.height // 2)
            fill = track.copy()
            fill.width = max(track.height, round(bar_w * min(value, STAT_BAR_MAX) / STAT_BAR_MAX))
            pygame.draw.rect(
                self.screen, theme.stat_color(value), fill, border_radius=track.height // 2
            )
        cy = round(rows_top + row_h * (len(stats) + 0.5))
        self.text("TOTAL", self.font_tiny, theme.muted, (rect.left, cy), "midleft")
        self.text(
            str(mon.stats.total),
            self.font_bold,
            theme.text,
            (bar_left - self.px(6), cy),
            "midright",
        )

    def _type_badges(self, mon: Pokemon, pos: tuple[int, int], anchor: Anchor) -> pygame.Rect:
        """Draw the type badges side by side; anchor positions the whole group."""
        surfaces = [self._badge_surface(t.upper(), self.theme.type_color(t)) for t in mon.types]
        gap = self.px(4)
        width = sum(s.get_width() for s in surfaces) + gap * (len(surfaces) - 1)
        group = pygame.Rect(0, 0, width, surfaces[0].get_height())
        setattr(group, anchor, pos)
        x = group.left
        for surface in surfaces:
            self.screen.blit(surface, (x, group.top))
            x += surface.get_width() + gap
        return group

    def badge(self, label: str, color: Color, pos: tuple[int, int], anchor: Anchor) -> pygame.Rect:
        surface = self._badge_surface(label, color)
        rect = surface.get_rect(**{anchor: pos})
        self.screen.blit(surface, rect)
        return rect

    def _badge_surface(self, label: str, color: Color) -> pygame.Surface:
        text = self.font_tiny.render(label, True, self.theme.ink_on(color))
        surface = pygame.Surface(
            (text.get_width() + self.px(14), text.get_height() + self.px(5)), pygame.SRCALPHA
        )
        pygame.draw.rect(
            surface, color, surface.get_rect(), border_radius=surface.get_height() // 2
        )
        surface.blit(text, text.get_rect(center=surface.get_rect().center))
        return surface

    def _scrollbar(self, track: pygame.Rect, top: int, shown: int, total: int) -> None:
        pygame.draw.rect(self.screen, self.theme.panel, track, border_radius=track.width)
        thumb = track.copy()
        thumb.height = max(self.px(12), round(track.height * shown / total))
        thumb.top = track.top + round((track.height - thumb.height) * top / (total - shown))
        pygame.draw.rect(self.screen, self.theme.muted, thumb, border_radius=track.width)

    def _placeholder(self, center: tuple[int, int], radius: int) -> None:
        pygame.draw.circle(self.screen, self.theme.panel_light, center, radius)
        self.text("?", self.font_title, self.theme.muted, center, "center")

    def _footer_hints(self, hints: list[str], right: str = "") -> None:
        footer = self.footer
        x = footer.left + self.px(10)
        for hint in filter(None, hints):
            x = self.text(
                hint, self.font_small, self.theme.muted, (x, footer.centery), "midleft"
            ).right + self.px(14)
        if right:
            pos = (footer.right - self.px(10), footer.centery)
            self.text(right, self.font_small, self.theme.muted, pos, "midright")

    # Text helpers

    def text(
        self, text: str, font: pygame.font.Font, color: Color, pos: tuple[int, int], anchor: Anchor
    ) -> pygame.Rect:
        surface = font.render(text, True, color)
        rect = surface.get_rect(**{anchor: pos})
        self.screen.blit(surface, rect)
        return rect

    def paragraph(self, text: str, font: pygame.font.Font, color: Color, rect: pygame.Rect) -> None:
        """Word-wrap text into rect, ending with an ellipsis if it does not fit."""
        line_h = font.get_linesize()
        max_lines = max(1, rect.height // line_h)
        lines = wrap(text, font, rect.width)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = ellipsize(lines[-1] + "…", font, rect.width)
        for i, line in enumerate(lines):
            self.screen.blit(font.render(line, True, color), (rect.left, rect.top + i * line_h))


def wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.size(candidate)[0] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def ellipsize(text: str, font: pygame.font.Font, width: int) -> str:
    while font.size(text)[0] > width and len(text) > 1:
        text = text[:-2] + "…"
    return text
