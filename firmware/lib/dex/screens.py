"""Drawing the home, list, entry, evolution, search and settings screens with displayio.

Laid out for 480x320. Each screen builds its shapes and labels once when it
opens, then update() only changes what moved: displayio resends just the
changed areas, which matters because redrawing the whole SPI screen is slow.
"""

import gc
import math

import displayio
import terminalio
import vectorio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label, wrap_text_to_pixels

from dex import battery, evolution, keyboard, state, theme
from dex.index import REGIONS
from dex.settings import KEY, KIND, LABEL
from dex.settings import ROWS as SETTING_ROWS
from dex.units import format_height, format_weight

W, H = 480, 320
HEADER_H = 30
FOOTER_H = 18
PAD = 8
BODY_X, BODY_Y = PAD, HEADER_H + PAD
BODY_W, BODY_H = W - 2 * PAD, H - FOOTER_H - PAD - BODY_Y
OFFSCREEN = -1000
"""x for shapes that are hidden for now (vectorio shapes can't be hidden directly).
Far enough left that even a full-width shape stays off the screen."""
HEADER_RIGHT = W - 44
"""Right edge for header text, leaving room for the battery icon."""
STAT_BAR_MAX = 200  # base stats above this fill the whole bar

FONT_FILES = {
    "title": "title.bdf",  # DejaVu Sans Bold 18
    "name": "name.bdf",  # DejaVu Sans Bold 16
    "body": "body.bdf",  # DejaVu Sans 13
    "bold": "bold.bdf",  # DejaVu Sans Bold 12
    "small": "small.bdf",  # DejaVu Sans 11
}


class Fonts:
    """Bitmap fonts from the SD card; the built-in font stands in for any missing one."""

    def __init__(self, folder=None):
        for attr, filename in FONT_FILES.items():
            font = terminalio.FONT
            if folder:
                try:
                    font = bitmap_font.load_font(folder + "/" + filename)
                    font.load_glyphs(
                        " 0123456789#abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    )
                except (OSError, ValueError):
                    font = terminalio.FONT
            setattr(self, attr, font)


# Drawing helpers

_palettes = {}


def palette(color):
    """A shared one-colour palette for vectorio shapes."""
    if color not in _palettes:
        p = displayio.Palette(1)
        p[0] = color
        _palettes[color] = p
    return _palettes[color]


def rect(group, x, y, w, h, color):
    shape = vectorio.Rectangle(pixel_shader=palette(color), width=w, height=h, x=x, y=y)
    group.append(shape)
    return shape


def circle(group, cx, cy, r, color):
    shape = vectorio.Circle(pixel_shader=palette(color), radius=r, x=cx, y=cy)
    group.append(shape)
    return shape


def text(group, font, s, color, x, y, anchor=(0, 0.5), line_spacing=1.0):
    label = bitmap_label.Label(
        font,
        text=s,
        color=color,
        anchor_point=anchor,
        anchored_position=(x, y),
        line_spacing=line_spacing,
        # Anchor on the text's own ink. The default box is as tall as the font's
        # tallest glyph (É, ♀), which draws ordinary text several pixels low.
        background_tight=True,
    )
    group.append(label)
    return label


def text_width(label):
    return label.bounding_box[2] if label.text else 0


def set_text(label, s):
    """Change a label only if its text differs: any change redraws that area."""
    if label.text != s:
        label.text = s


def fit(label, max_width):
    """Shorten a label's text with "…" until it is at most max_width pixels wide."""
    text = label.text
    while text and text_width(label) > max_width:
        text = text[:-1].rstrip()
        label.text = text + "…"


def set_color(label, color):
    if label.color != color:
        label.color = color


def image(path, cx, cy):
    """A BMP from the SD card centred on (cx, cy); colour 0 is transparent. None if missing."""
    try:
        bitmap = displayio.OnDiskBitmap(path)
    except (OSError, ValueError):
        return None
    shader = bitmap.pixel_shader
    if isinstance(shader, displayio.Palette):
        shader.make_transparent(0)
    return displayio.TileGrid(
        bitmap, pixel_shader=shader, x=cx - bitmap.width // 2, y=cy - bitmap.height // 2
    )


def replace(slot, item):
    """Put item (or nothing) in a one-item group, dropping what was there."""
    while len(slot):
        slot.pop()
    if item is not None:
        slot.append(item)
    gc.collect()


def number(pokemon_id):
    return f"{pokemon_id:03d}"


class Badge:
    """A coloured label, e.g. FIRE on orange: set() what it says, then place() it."""

    HEIGHT = 16

    def __init__(self, group, font, cy):
        self._cy = cy
        self.rect = rect(group, OFFSCREEN, cy - self.HEIGHT // 2, 1, self.HEIGHT, theme.PANEL)
        self.label = text(group, font, "", theme.TEXT, OFFSCREEN, cy, (0.5, 0.5))
        self.width = 0

    def set(self, label, color):
        """Show label on color; an empty label hides the badge."""
        set_text(self.label, label)
        if not label:
            self.width = 0
            self.place(OFFSCREEN)
            return
        set_color(self.label, theme.ink_on(color))
        self.rect.pixel_shader = palette(color)
        self.width = text_width(self.label) + 12
        self.rect.width = self.width

    def place(self, left):
        self.rect.x = left
        self.label.anchored_position = (left + self.width // 2, self._cy)

    def move_to_row(self, cy):
        self._cy = cy
        self.rect.y = cy - self.HEIGHT // 2


class TypeBadges:
    """One or two type badges in a row starting at x (or centred on it)."""

    GAP = 4

    def __init__(self, group, font, x, cy, centered=False):
        self.x, self.centered = x, centered
        self.badges = (Badge(group, font, cy), Badge(group, font, cy))

    def set(self, types):
        """Show the types; returns the row's width."""
        names = list(types) + [""] * (2 - len(types))
        for badge, name in zip(self.badges, names):
            badge.set(name.upper(), theme.type_color(name) if name else 0)
        total = sum(b.width for b in self.badges) + (self.GAP if len(types) > 1 else 0)
        x = self.x - total // 2 if self.centered else self.x
        for badge in self.badges:
            if badge.width:
                badge.place(x)
                x += badge.width + self.GAP
        return total


def header(group, fonts, title):
    """The red header bar with the Pokédex's blue lens; returns the title label."""
    rect(group, 0, 0, W, HEADER_H, theme.ACCENT)
    circle(group, 16, HEADER_H // 2, 8, theme.WHITE)
    circle(group, 16, HEADER_H // 2, 6, theme.LENS)
    return text(group, fonts.title, title, theme.TEXT, 30, HEADER_H // 2)


def footer(group, fonts, hints, right=""):
    """Button hints along the bottom; returns (hints label, right label)."""
    y = H - FOOTER_H // 2
    left = text(group, fonts.small, hints, theme.MUTED, PAD, y)
    right_label = text(group, fonts.small, right, theme.MUTED, W - PAD, y, (1, 0.5))
    return left, right_label


# Screens


class Screen:
    def __init__(self, ui):
        self.ui = ui
        self.fonts = ui.fonts
        self.group = displayio.Group()

    def update(self, st):
        pass


class HomeScreen(Screen):
    ROW_H = 44
    GAP = 7

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        header(g, fonts, "POKÉDEX")
        count = len(state.MENU)
        self.top = BODY_Y + (BODY_H - (self.ROW_H * count + self.GAP * (count - 1))) // 2
        for i in range(count):
            rect(g, BODY_X, self._row_y(i), BODY_W, self.ROW_H, theme.PANEL)
        self.highlight = rect(g, BODY_X, self._row_y(0), BODY_W, self.ROW_H, theme.ACCENT)
        self.subtitles = []
        for i, (title, _) in enumerate(state.MENU):
            y = self._row_y(i) + self.ROW_H // 2
            text(g, fonts.name, title, theme.TEXT, BODY_X + 20, y - 9)
            self.subtitles.append(text(g, fonts.small, "", theme.MUTED, BODY_X + 20, y + 11))
        footer(g, fonts, "▲▼ choose    A open    START menu, from anywhere")

    def _row_y(self, i):
        return self.top + i * (self.ROW_H + self.GAP)

    def update(self, st):
        settings = st.settings
        quiz = st.quiz
        subtitles = (
            f"{len(st.dex)} entries",
            "Find by name or number",
            f"{st.browse.count} picked"
            if st.browse and st.browse.count
            else "Colour, shape, size...",
            f"Score {quiz.score}/{quiz.asked}" if quiz and quiz.asked else "Who's that Pokémon?",
            "Volume {} · Sound {}".format(settings.describe("volume"), settings.describe("sound")),
        )
        for i, label in enumerate(self.subtitles):
            set_text(label, subtitles[i])
            set_color(label, theme.TEXT if i == st.menu_index else theme.MUTED)
        self.highlight.y = self._row_y(st.menu_index)


class ListScreen(Screen):
    ROWS = 9
    ROW_H = 28
    PREVIEW_W = 186
    TEXT_H = 58
    """Room under the preview's sprite for the number, name and types."""

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        header(g, fonts, "POKÉDEX")
        self.count = text(g, fonts.body, "", theme.TEXT, HEADER_RIGHT, HEADER_H // 2, (1, 0.5))
        self.filter = Badge(g, fonts.bold, HEADER_H // 2)
        self.region = Badge(g, fonts.bold, HEADER_H // 2)
        self.picks = Badge(g, fonts.bold, HEADER_H // 2)
        """How many browse values are picked, e.g. "✓ 2"."""

        # Preview of the selected Pokémon, on the left.
        rect(g, BODY_X, BODY_Y, self.PREVIEW_W, BODY_H, theme.PANEL)
        self.sprite_center = (BODY_X + self.PREVIEW_W // 2, BODY_Y + (BODY_H - self.TEXT_H) // 2)
        self.sprite = displayio.Group()
        g.append(self.sprite)
        cx, y = BODY_X + self.PREVIEW_W // 2, BODY_Y + BODY_H - self.TEXT_H
        self.preview_number = text(g, fonts.small, "", theme.MUTED, cx, y, (0.5, 0.5))
        self.preview_name = text(g, fonts.name, "", theme.TEXT, cx, y + 16, (0.5, 0.5))
        self.preview_types = TypeBadges(g, fonts.bold, cx, y + 37, centered=True)

        # The list, on the right.
        self.rows_x = BODY_X + self.PREVIEW_W + PAD
        self.rows_w = BODY_X + BODY_W - self.rows_x - 6
        self.highlight = rect(g, self.rows_x, BODY_Y, self.rows_w, self.ROW_H, theme.ACCENT)
        self.rows = []
        for row in range(self.ROWS):
            cy = BODY_Y + row * self.ROW_H + self.ROW_H // 2
            dots = (
                circle(g, OFFSCREEN, cy, 4, theme.MUTED),
                circle(g, OFFSCREEN, cy, 4, theme.MUTED),
            )
            self.rows.append(
                (
                    text(g, fonts.bold, "", theme.MUTED, self.rows_x + 8, cy),
                    text(g, fonts.body, "", theme.TEXT, self.rows_x + 44, cy),
                    dots,
                )
            )
        track_x = BODY_X + BODY_W - 3
        rect(g, track_x, BODY_Y, 3, self.ROWS * self.ROW_H, theme.PANEL)
        self.thumb = rect(g, track_x, BODY_Y, 3, 10, theme.MUTED)
        self.hints = footer(g, fonts, "")[0]
        st.page_size = self.ROWS
        self._shown = None
        """(first row's position, filter) last drawn, to skip unchanged rows."""
        self._preview_pos = None

    def update(self, st):
        total = len(st.visible)
        set_text(self.count, str(total))
        # "ALL" when nothing is filtered; otherwise the other badges say enough.
        label = (st.type_filter or ("" if st.filtered else "all")).upper()
        color = theme.type_color(st.type_filter) if st.type_filter else theme.PANEL_LIGHT
        self.filter.set(label, color)
        right = HEADER_RIGHT - text_width(self.count) - 8
        if self.filter.width:
            self.filter.place(right - self.filter.width)
            right -= self.filter.width + 4
        self.region.set(st.region_name.upper(), theme.PANEL_LIGHT)
        if self.region.width:
            self.region.place(right - self.region.width)
            right -= self.region.width + 4
        picked = st.browse.count if st.browse else 0
        self.picks.set(f"✓ {picked}" if picked else "", theme.RIGHT)
        if self.picks.width:
            self.picks.place(right - self.picks.width)

        top = max(0, min(st.index - self.ROWS // 2, total - self.ROWS))
        shown = (top, st.type_filter, st.region_filter, picked, len(st.visible))
        if self._shown != shown:
            self._shown = shown
            self._draw_rows(st, top)
        selected_row = st.index - top
        self.highlight.y = BODY_Y + selected_row * self.ROW_H
        for row, (num, _, _) in enumerate(self.rows):
            set_color(num, theme.TEXT if row == selected_row else theme.MUTED)

        if total > self.ROWS:
            track = self.ROWS * self.ROW_H
            self.thumb.height = max(10, track * self.ROWS // total)
            self.thumb.y = BODY_Y + (track - self.thumb.height) * top // (total - self.ROWS)
        else:
            self.thumb.y = OFFSCREEN

        if (st.selected, self.ui.shiny) != self._preview_pos:
            self._preview_pos = (st.selected, self.ui.shiny)
            self._draw_preview(st)
        hints = "▲▼ move  ◀▶ page  A open  L/R type  SEL region"
        set_text(self.hints, hints + ("  B all" if st.filtered else ""))

    def _draw_rows(self, st, top):
        dex = st.dex
        for row, (num, name, dots) in enumerate(self.rows):
            i = top + row
            if i >= len(st.visible):
                set_text(num, "")
                set_text(name, "")
                for dot in dots:
                    dot.x = OFFSCREEN
                continue
            pos = st.visible[i]
            set_text(num, number(dex.ids[pos]))
            set_text(name, dex.names[pos])
            types = dex.types(pos)
            x = self.rows_x + self.rows_w - 10 - 12 * (len(types) - 1)
            for dot, type_name in zip(dots, types + ("",)):
                if type_name:
                    dot.pixel_shader = palette(theme.type_color(type_name))
                    dot.x = x
                    x += 12
                else:
                    dot.x = OFFSCREEN

    def _draw_preview(self, st):
        pos = st.selected
        if pos is None:
            replace(self.sprite, None)
            self.preview_number.text = ""
            self.preview_name.text = "No Pokémon"
            self.preview_types.set(())
            return
        pokemon_id = st.dex.ids[pos]
        replace(self.sprite, image(self.ui.picture("spr", pokemon_id), *self.sprite_center))
        self.preview_number.text = "#" + number(pokemon_id)
        self.preview_name.text = st.dex.names[pos]
        self.preview_types.set(st.dex.types(pos))


MATCHUP_SECTIONS = (
    ("Weak to", ("4", "2")),
    ("Resists", ("0.5", "0.25")),
    ("Not affected by", ("0",)),
)
MULTIPLIER_LABELS = {"4": " ×4", "2": "", "0.5": "", "0.25": " ×¼", "0": ""}
"""Extra text on a matchup badge: ×4 and ×¼ stand out from the usual ×2 and ×½."""


class DetailScreen(Screen):
    """An entry, in four tabs switched with LEFT/RIGHT: info, type matchups, abilities, moves.

    The artwork stays on the left; the tab fills the rest.
    """

    FLAVOR_H = 58
    ART = 190
    FLAVOR_LINES = 3
    MOVE_ROW_H = 19

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        self.title = header(g, fonts, "")
        self.genus = text(g, fonts.body, "", theme.TEXT, HEADER_RIGHT, HEADER_H // 2, (1, 0.5))

        top_h = BODY_H - self.FLAVOR_H - PAD
        art = min(self.ART, top_h)
        self.art_center = (BODY_X + art // 2, BODY_Y + top_h // 2)
        circle(g, self.art_center[0], self.art_center[1], art // 2, theme.PANEL)
        self.art = displayio.Group()
        g.append(self.art)
        self.tab_x = BODY_X + art + 2 * PAD
        self.tab_w = BODY_X + BODY_W - self.tab_x
        st.move_rows = (BODY_H - 22) // self.MOVE_ROW_H

        # INFO: types, size, stats and the Pokédex text.
        self.info = displayio.Group()
        g.append(self.info)
        x, right = self.tab_x, BODY_X + BODY_W
        self.types = TypeBadges(self.info, fonts.bold, x, BODY_Y + 9)
        self.measures = text(self.info, fonts.body, "", theme.MUTED, x, BODY_Y + 9)
        rows_top = BODY_Y + 26
        row_h = (BODY_Y + top_h - rows_top) // (len(theme.STAT_LABELS) + 1)
        self.bar_x = x + 84
        self.bar_w = right - self.bar_x
        self.stats = []
        for i, label in enumerate(theme.STAT_LABELS + ("TOTAL",)):
            cy = rows_top + i * row_h + row_h // 2
            text(self.info, fonts.bold, label, theme.MUTED, x, cy)
            value = text(self.info, fonts.body, "", theme.TEXT, x + 76, cy, (1, 0.5))
            bar = None
            if i < len(theme.STAT_LABELS):
                rect(self.info, self.bar_x, cy - 4, self.bar_w, 8, theme.PANEL)
                bar = rect(self.info, self.bar_x, cy - 4, 1, 8, theme.MUTED)
            self.stats.append((value, bar))
        flavor_y = BODY_Y + BODY_H - self.FLAVOR_H
        rect(self.info, BODY_X, flavor_y, BODY_W, self.FLAVOR_H, theme.PANEL)
        self.flavor = text(
            self.info,
            fonts.body,
            "",
            theme.TEXT,
            BODY_X + 8,
            flavor_y + 5,
            (0, 0),
            line_spacing=1.1,
        )

        # The other tabs, built when shown; plus the region under the artwork.
        self.tab = displayio.Group()
        g.append(self.tab)
        self.region = text(
            g, fonts.bold, "", theme.MUTED, self.art_center[0], flavor_y + 29, (0.5, 0.5)
        )

        # Footer: the tab names, the current one lit, and the position in the list.
        y = H - FOOTER_H // 2
        self.tab_labels = []
        x = PAD
        for name in state.TABS:
            label = text(g, fonts.small, name, theme.MUTED, x, y)
            self.tab_labels.append(label)
            x += text_width(label) + 14
        self.position = text(g, fonts.small, "", theme.MUTED, W - PAD, y, (1, 0.5))
        self._shown = None
        self._shown_tab = None

    def update(self, st):
        pokemon_id = st.selected_id
        position = f"{st.index + 1}/{len(st.visible)}"
        set_text(self.position, position if st.settings.sound else "MUTED   " + position)
        for i, label in enumerate(self.tab_labels):
            set_color(label, theme.TEXT if i == st.tab else theme.MUTED)
        entry = st.entry
        shown = (pokemon_id, st.settings.units, self.ui.shiny)
        if shown != self._shown:
            self._shown = shown
            self._shown_tab = None
            self._draw_info(st, entry)
        tab = (st.tab, st.move_scroll)
        if tab != self._shown_tab:
            self._shown_tab = tab
            self.info.hidden = st.tab != state.INFO
            replace(self.tab, self._build_tab(st, entry))
            region = REGIONS[entry.get("region") or 0] if entry else ""
            set_text(self.region, region if st.tab != state.INFO else "")

    def _draw_info(self, st, entry):
        pokemon_id, pos = st.selected_id, st.selected
        self.title.text = f"#{number(pokemon_id)}  {st.dex.names[pos]}"
        replace(self.art, image(self.ui.picture("art", pokemon_id), *self.art_center))
        width = self.types.set(st.dex.types(pos))
        self.measures.anchored_position = (self.types.x + width + 10, BODY_Y + 9)
        if entry is None:
            self.genus.text = ""
            self.measures.text = ""
            self.flavor.text = "This entry is missing from the SD card."
            for value, bar in self.stats:
                value.text = ""
                if bar:
                    bar.width = 1
            return
        self.genus.text = entry.get("genus") or ""
        units = st.settings.units
        self.measures.text = "{}   {}".format(
            format_height(entry["height_dm"], units), format_weight(entry["weight_hg"], units)
        )
        values = list(entry["stats"]) + [sum(entry["stats"])]
        for (label, bar), value in zip(self.stats, values):
            label.text = str(value)
            if bar:
                bar.width = max(1, self.bar_w * min(value, STAT_BAR_MAX) // STAT_BAR_MAX)
                bar.pixel_shader = palette(theme.stat_color(value))
        lines = wrap_text_to_pixels(entry.get("flavor") or "", BODY_W - 16, self.fonts.body)
        self.flavor.text = "\n".join(lines[: self.FLAVOR_LINES])

    def _build_tab(self, st, entry):
        if st.tab == state.INFO:
            return None
        group = displayio.Group()
        key = {state.MATCHUPS: "matchups", state.ABILITIES: "abilities", state.MOVES: "moves"}
        if not entry or not entry.get(key[st.tab]):
            message = "Not on this SD card yet. Rebuild it with the latest pokedex-fetch."
            lines = wrap_text_to_pixels(message, self.tab_w, self.fonts.body)
            text(group, self.fonts.body, "\n".join(lines), theme.MUTED, self.tab_x, BODY_Y, (0, 0))
            return group
        if st.tab == state.MATCHUPS:
            self._matchups(group, entry["matchups"])
        elif st.tab == state.ABILITIES:
            self._abilities(group, entry["abilities"])
        else:
            self._moves(group, entry, st.move_scroll)
        return group

    def _matchups(self, group, matchups):
        fonts, x0, right = self.fonts, self.tab_x, self.tab_x + self.tab_w
        y = BODY_Y + 6
        for title, keys in MATCHUP_SECTIONS:
            text(group, fonts.bold, title, theme.MUTED, x0, y)
            y += 18
            types = [(t, key) for key in keys for t in matchups.get(key, ())]
            if not types:
                text(group, fonts.body, "None", theme.MUTED, x0, y)
                y += 26
                continue
            x = x0
            for type_name, key in types:
                label = type_name.upper() + MULTIPLIER_LABELS[key]
                badge = Badge(group, fonts.bold, y)
                badge.set(label, theme.type_color(type_name))
                if x + badge.width > right:  # wrap onto the next row
                    x, y = x0, y + Badge.HEIGHT + 4
                    badge.move_to_row(y)
                badge.place(x)
                x += badge.width + 4
            y += Badge.HEIGHT + 14

    def _abilities(self, group, abilities):
        fonts, x = self.fonts, self.tab_x
        y = BODY_Y + 6
        for name, hidden, description in abilities:
            label = text(group, fonts.name, name, theme.TEXT, x, y)
            if hidden:
                text(
                    group, fonts.small, "hidden ability", theme.MUTED, x + text_width(label) + 8, y
                )
            y += 12
            lines = wrap_text_to_pixels(description, self.tab_w, fonts.small)[:3]
            if lines:
                text(group, fonts.small, "\n".join(lines), theme.MUTED, x, y, (0, 0))
            y += 14 * len(lines) + 16

    def _moves(self, group, entry, scroll):
        fonts, x, right = self.fonts, self.tab_x, self.tab_x + self.tab_w
        moves = entry["moves"]
        rows = (BODY_H - 22) // self.MOVE_ROW_H
        shown = moves[scroll : scroll + rows]
        heading = "Level-up moves · " + (entry.get("moves_from") or "")
        fit(text(group, fonts.small, heading, theme.MUTED, x, BODY_Y + 6), self.tab_w - 60)
        if len(moves) > rows:
            more = f"{scroll + 1}-{scroll + len(shown)} of {len(moves)}"
            text(group, fonts.small, more, theme.MUTED, right, BODY_Y + 6, (1, 0.5))
        for i, (level, name, type_name, power) in enumerate(shown):
            cy = BODY_Y + 22 + i * self.MOVE_ROW_H + self.MOVE_ROW_H // 2
            when = "Evo" if level == 0 else str(level)
            text(group, fonts.bold, when, theme.MUTED, x + 24, cy, (1, 0.5))
            circle(group, x + 34, cy, 4, theme.type_color(type_name))
            label = text(group, fonts.body, name, theme.TEXT, x + 44, cy)
            fit(label, self.tab_w - 84)
            if power:
                text(group, fonts.body, str(power), theme.MUTED, right, cy, (1, 0.5))


class EvolutionScreen(Screen):
    """The family as a map: a column per stage, arrows from each Pokémon to what it becomes."""

    TEXT_H = 30
    """Room under a card's picture for its subtitle and name."""
    PICTURE_SIZES = (72, 44, 26)
    """Evolution pictures on the card, in folders ev72/, ev44/ and ev26/."""
    ARROW_HEAD = 7

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        header(g, fonts, f"#{number(st.selected_id)}  {st.dex.names[st.selected]}")
        text(g, fonts.bold, "EVOLUTION", theme.TEXT, HEADER_RIGHT, HEADER_H // 2, (1, 0.5))
        self.cells = {}
        self.cursor = ()

        chain = st.chain
        if chain is None:
            cx, cy = W // 2, BODY_Y + BODY_H // 2
            text(g, fonts.name, "No evolution data on the card.", theme.TEXT, cx, cy, (0.5, 0.5))
            footer(g, fonts, "B back")
            return

        stages = evolution.stages(chain)
        self.cells, compact = evolution.layout(stages, BODY_X, BODY_Y, BODY_W, BODY_H)
        branched = evolution.branched(stages)
        for step in chain["steps"]:
            label = "" if step[1] in branched else step[3]
            self._arrow(self.cells[step[0]], self.cells[step[1]], label)
        for species_id, cell in self.cells.items():
            method = evolution.method(chain, species_id) if species_id in branched else None
            self._card(st, chain, species_id, cell, species_id in compact, method)
        # The cursor: an accent outline, moved by update().
        self.cursor = tuple(rect(g, OFFSCREEN, 0, 2, 2, theme.ACCENT) for _ in range(4))

        if len(stages) == 1:
            x, y, w, h = self.cells[chain["root"]]
            text(g, fonts.body, "Doesn't evolve.", theme.MUTED, x + w // 2, y + h + 14, (0.5, 0.5))
        moves = "◀▶ move" if len(stages) > 1 else ""
        if any(len(stage) > 1 for stage in stages):
            moves = "▲▼◀▶ move"
        footer(g, fonts, "    ".join(hint for hint in (moves, "A open", "B back") if hint))

    def _card(self, st, chain, species_id, cell, compact, method):
        """A species card; method, when given, replaces the Pokédex number."""
        g, fonts = self.group, self.fonts
        x, y, w, h = cell[0] + 2, cell[1] + 2, cell[2] - 4, cell[3] - 4
        rect(g, x, y, w, h, theme.PANEL)
        on_card = st.dex.position(species_id) is not None
        ink = theme.TEXT if on_card else theme.MUTED
        name = evolution.name(chain, species_id)

        if compact:
            # One-line row for wide branches (Eevee): picture, name, and how it evolves.
            size = h
            cx = x + size // 2 + 2
            self._picture(species_id, on_card, size, cx, y + h // 2)
            left = cx + size // 2 + 4
            room = x + w - left - 4
            name_y = y + h // 2 - 6 if method else y + h // 2
            if method:
                fit(text(g, fonts.small, method, theme.MUTED, left, name_y + 12), room)
            fit(text(g, fonts.bold, name, ink, left, name_y), room)
            return

        size = min(w, h - self.TEXT_H) - 6
        self._picture(species_id, on_card, size, x + w // 2, y + 3 + (h - self.TEXT_H) // 2)
        subtitle_y = y + h - self.TEXT_H + 6
        subtitle = method or "#" + number(species_id)
        cx = x + w // 2
        fit(text(g, fonts.small, subtitle, theme.MUTED, cx, subtitle_y, (0.5, 0.5)), w - 6)
        fit(text(g, fonts.bold, name, ink, cx, subtitle_y + 13, (0.5, 0.5)), w - 6)

    def _picture(self, species_id, on_card, size, cx, cy):
        """The largest evolution picture that fits; a grey dot for species not on the card."""
        fitting = [s for s in self.PICTURE_SIZES if s <= size]
        picture = None
        if on_card and fitting:
            picture = image(self.ui.picture(f"ev{fitting[0]}", species_id), cx, cy)
        if picture is not None:
            self.group.append(picture)
        else:
            circle(self.group, cx, cy, max(3, size // 3), theme.PANEL_LIGHT)

    def _arrow(self, parent, child, label):
        """A line from the parent card's right edge to the child's left edge, with a head."""
        sx, sy = parent[0] + parent[2] - 1, parent[1] + parent[3] // 2
        ex, ey = child[0] + 1, child[1] + child[3] // 2
        dx, dy = ex - sx, ey - sy
        length = math.sqrt(dx * dx + dy * dy) or 1
        ux, uy = dx / length, dy / length  # along the arrow
        nx, ny = -uy, ux  # across it
        head = self.ARROW_HEAD
        bx, by = ex - ux * head, ey - uy * head  # where the head starts
        shader = palette(theme.MUTED)
        self.group.append(
            vectorio.Polygon(
                pixel_shader=shader,
                points=[
                    (round(sx + nx), round(sy + ny)),
                    (round(bx + nx), round(by + ny)),
                    (round(bx - nx), round(by - ny)),
                    (round(sx - nx), round(sy - ny)),
                ],
                x=0,
                y=0,
            )
        )
        self.group.append(
            vectorio.Polygon(
                pixel_shader=shader,
                points=[
                    (ex, ey),
                    (round(bx + nx * head * 0.6), round(by + ny * head * 0.6)),
                    (round(bx - nx * head * 0.6), round(by - ny * head * 0.6)),
                ],
                x=0,
                y=0,
            )
        )
        if not label:
            return
        # Up to three lines above the arrow's middle, bottom line first.
        width = ex - sx - 10
        lines = wrap_text_to_pixels(label, width, self.fonts.small)[:3]
        mx, bottom = (sx + ex) // 2, (sy + ey) // 2 - 4
        for i, line in enumerate(reversed(lines)):
            label = text(
                self.group, self.fonts.small, line, theme.TEXT, mx, bottom - i * 13, (0.5, 1)
            )
            fit(label, width)

    def update(self, st):
        cell = self.cells.get(st.evo_cursor)
        if not cell or not self.cursor:
            return
        x, y, w, h = cell[0] + 2, cell[1] + 2, cell[2] - 4, cell[3] - 4
        for shape, (sx, sy, sw, sh) in zip(
            self.cursor, ((x, y, w, 2), (x, y + h - 2, w, 2), (x, y, 2, h), (x + w - 2, y, 2, h))
        ):
            shape.x, shape.y, shape.width, shape.height = sx, sy, sw, sh


class SearchScreen(Screen):
    KEY_W = 30
    KEY_H = 36
    KEY_GAP = 4
    RESULT_ROWS = 9
    RESULT_H = 28

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        header(g, fonts, "SEARCH")
        kb_w = keyboard.COLUMNS * self.KEY_W
        rect(g, BODY_X, BODY_Y, kb_w - self.KEY_GAP, 28, theme.PANEL)
        self.query = text(g, fonts.name, "", theme.TEXT, BODY_X + 8, BODY_Y + 14)

        self.kb_y = BODY_Y + 36
        for row, keys in enumerate(keyboard.LAYOUT):
            for index in range(len(keys)):
                x, y, w = self._key_box(row, index)
                rect(g, x, y, w, self.KEY_H, theme.PANEL)
        self.key_highlight = rect(g, BODY_X, self.kb_y, self.KEY_W, self.KEY_H, theme.ACCENT)
        for row, keys in enumerate(keyboard.LAYOUT):
            for index, key in enumerate(keys):
                x, y, w = self._key_box(row, index)
                font = fonts.bold if key[keyboard.SPAN] > 1 else fonts.name
                text(g, font, key[keyboard.LABEL], theme.TEXT, x + w // 2, y + 18, (0.5, 0.5))

        self.results_x = BODY_X + kb_w + PAD
        self.results_w = BODY_X + BODY_W - self.results_x
        rect(g, self.results_x, BODY_Y, self.results_w, BODY_H, theme.PANEL)
        self.result_highlight = rect(
            g, OFFSCREEN, BODY_Y, self.results_w, self.RESULT_H, theme.PANEL_LIGHT
        )
        self.results = [
            text(g, fonts.body, "", theme.TEXT, self.results_x + 8, self._result_y(i))
            for i in range(self.RESULT_ROWS)
        ]
        self.hints = footer(g, fonts, "")[0]

    def _key_box(self, row, index):
        span = keyboard.LAYOUT[row][index][keyboard.SPAN]
        x = BODY_X + keyboard.column_of(row, index) * self.KEY_W
        y = self.kb_y + row * (self.KEY_H + self.KEY_GAP)
        return x, y, span * self.KEY_W - self.KEY_GAP

    def _result_y(self, i):
        return BODY_Y + i * self.RESULT_H + self.RESULT_H // 2

    def update(self, st):
        s = st.search
        set_text(self.query, s.query.upper() + "_")
        x, y, w = self._key_box(s.key_row, s.key_index)
        self.key_highlight.x, self.key_highlight.y, self.key_highlight.width = x, y, w
        self.key_highlight.pixel_shader = palette(
            theme.PANEL_LIGHT if s.in_results else theme.ACCENT
        )

        total = len(s.results)
        top = max(0, min(s.result_index - self.RESULT_ROWS // 2, total - self.RESULT_ROWS))
        for i, label in enumerate(self.results):
            if top + i < total:
                pos = s.results[top + i]
                set_text(label, number(st.dex.ids[pos]) + " " + st.dex.names[pos])
                set_color(label, theme.TEXT)
            elif i == 0 and s.query:
                set_text(label, "No matches")
                set_color(label, theme.MUTED)
            else:
                set_text(label, "")
        if s.in_results and total:
            self.result_highlight.x = self.results_x
            self.result_highlight.y = BODY_Y + (s.result_index - top) * self.RESULT_H
            self.result_highlight.pixel_shader = palette(theme.ACCENT)
        else:
            self.result_highlight.x = OFFSCREEN
        if s.in_results:
            set_text(self.hints, "▲▼ choose    A open    B keyboard")
        else:
            set_text(self.hints, "▲▼◀▶ key   A type   B delete   SEL results")


class SettingsScreen(Screen):
    ROW_H = 27
    GAP = 4

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        header(g, fonts, "SETTINGS")
        for i in range(len(SETTING_ROWS)):
            rect(g, BODY_X, self._row_y(i), BODY_W, self.ROW_H, theme.PANEL)
        self.highlight = rect(g, BODY_X, self._row_y(0), BODY_W, self.ROW_H, theme.ACCENT)
        self.values = []
        for i, row in enumerate(SETTING_ROWS):
            cy = self._row_y(i) + self.ROW_H // 2
            text(g, fonts.body, row[LABEL], theme.TEXT, BODY_X + 12, cy)
            value = text(g, fonts.bold, "", theme.TEXT, BODY_X + BODY_W - 12, cy, (1, 0.5))
            self.values.append(value)
        y = self._row_y(len(SETTING_ROWS)) + 4
        self.notice = text(g, fonts.small, "", theme.MUTED, BODY_X, y, (0, 0))
        footer(g, fonts, "▲▼ choose   ◀▶ change   A switch   B back")

    def _row_y(self, i):
        return BODY_Y + i * (self.ROW_H + self.GAP)

    def update(self, st):
        for i, row in enumerate(SETTING_ROWS):
            value = st.settings.describe(row[KEY])
            if row[KIND] in ("slider", "choice") and i == st.settings_index:
                value = "◀ " + value + " ▶"
            set_text(self.values[i], value)
        self.highlight.y = self._row_y(st.settings_index)
        set_text(self.notice, self.ui.notice)


class QuizScreen(Screen):
    """Who's that Pokémon? The silhouette on the left, four names on the right."""

    ART = 190
    CHOICE_H = 40
    GAP = 8

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        header(g, fonts, "WHO'S THAT POKÉMON?")
        self.score = text(g, fonts.body, "", theme.TEXT, HEADER_RIGHT, HEADER_H // 2, (1, 0.5))
        art = min(self.ART, BODY_H)
        self.art_center = (BODY_X + art // 2, BODY_Y + BODY_H // 2)
        circle(g, self.art_center[0], self.art_center[1], art // 2, theme.PANEL)
        self.art = displayio.Group()
        g.append(self.art)
        self.x = BODY_X + art + 2 * PAD
        self.w = BODY_X + BODY_W - self.x
        self.top = BODY_Y + 8
        self.boxes = []
        self.names = []
        for i in range(4):
            y = self.top + i * (self.CHOICE_H + self.GAP)
            self.boxes.append(rect(g, self.x, y, self.w, self.CHOICE_H, theme.PANEL))
            cy = y + self.CHOICE_H // 2
            self.names.append(text(g, fonts.name, "", theme.TEXT, self.x + 14, cy))
        message_y = self.top + 4 * (self.CHOICE_H + self.GAP) + 14
        cx = self.x + self.w // 2
        self.message = text(g, fonts.name, "", theme.TEXT, cx, message_y, (0.5, 0.5))
        self.hints = footer(g, fonts, "")[0]
        self._shown = None

    def update(self, st):
        quiz = st.quiz
        set_text(self.score, f"{quiz.score}/{quiz.asked}" if quiz.asked else "")
        shown = (quiz.target, quiz.answered, self.ui.shiny)
        if shown != self._shown:
            self._shown = shown
            pokemon_id = st.dex.ids[quiz.target]
            if quiz.answered:
                path = self.ui.picture("art", pokemon_id)
            else:
                path = self.ui.records.file("sil", pokemon_id, "bmp")
            replace(self.art, image(path, *self.art_center))
            for i, label in enumerate(self.names):
                set_text(label, st.dex.names[quiz.choices[i]] if i < len(quiz.choices) else "")
        for i, box in enumerate(self.boxes):
            color = theme.PANEL
            if i >= len(quiz.choices):
                color = theme.BG
            elif quiz.answered and quiz.choices[i] == quiz.target:
                color = theme.RIGHT
            elif i == quiz.cursor:
                color = theme.ACCENT
            box.pixel_shader = palette(color)
        if quiz.answered:
            name = st.dex.names[quiz.target]
            set_text(self.message, f"It's {name}!" if quiz.correct else f"No, it's {name}!")
            set_text(self.hints, "A next    B stop")
        else:
            set_text(self.message, "")
            set_text(self.hints, "▲▼ choose    A answer    B stop")


class BrowseScreen(Screen):
    """Categories, then a category's values: A picks (✓) or unpicks a value."""

    ROWS = 9
    ROW_H = 28

    def __init__(self, ui, st):
        super().__init__(ui)
        g, fonts = self.group, self.fonts
        rect(g, 0, 0, W, H, theme.BG)
        self.title = header(g, fonts, "BROWSE")
        self.matches = text(g, fonts.body, "", theme.TEXT, HEADER_RIGHT, HEADER_H // 2, (1, 0.5))
        st.value_rows = self.ROWS
        self.highlight = rect(g, BODY_X, BODY_Y, BODY_W - 6, self.ROW_H, theme.ACCENT)
        self.rows = []
        for row in range(self.ROWS):
            cy = BODY_Y + row * self.ROW_H + self.ROW_H // 2
            self.rows.append(
                (
                    text(g, fonts.bold, "", theme.RIGHT, BODY_X + 8, cy),
                    text(g, fonts.body, "", theme.TEXT, BODY_X + 28, cy),
                    text(g, fonts.small, "", theme.MUTED, BODY_X + BODY_W - 16, cy, (1, 0.5)),
                )
            )
        track_x = BODY_X + BODY_W - 3
        rect(g, track_x, BODY_Y, 3, self.ROWS * self.ROW_H, theme.PANEL)
        self.thumb = rect(g, track_x, BODY_Y, 3, 10, theme.MUTED)
        self.hints = footer(g, fonts, "")[0]

    def update(self, st):
        browse = st.browse
        set_text(self.matches, f"{len(st.visible)} match")
        if browse is None or not browse.categories:
            self._show_rows([("", "No categories on this SD card yet.", "")], -1)
            set_text(self.hints, "B back")
            return
        if st.browse_slug is None:
            set_text(self.title, "BROWSE")
            rows = [("", f"Show {len(st.visible)} Pokémon", "")]
            rows += [
                ("", label, browse.summary(slug)) for slug, label, _ in browse.shown_categories()
            ]
            self._show_rows(rows, st.browse_index)
            hints = "▲▼ choose   A open   B back"
            set_text(self.hints, hints + ("   SEL clear picks" if browse.count else ""))
            return
        label = next(c[1] for c in browse.categories if c[0] == st.browse_slug)
        set_text(self.title, label.upper())
        values = browse.values(st.browse_slug)
        counts = browse.counts(st.browse_slug)
        rows = [
            ("✓" if browse.is_picked(st.browse_slug, k) else "", values[k][0], str(counts[k]))
            for k in st.shown_values
        ]
        self._show_rows(rows, st.value_index)
        set_text(self.hints, "▲▼ move   A pick   ◀▶ page   L/R letter   B done")

    def _show_rows(self, rows, cursor):
        total = len(rows)
        top = max(0, min(cursor - self.ROWS // 2, total - self.ROWS))
        for i, (tick, name, right) in enumerate(self.rows):
            if top + i < total:
                row = rows[top + i]
                set_text(tick, row[0])
                set_text(name, row[1])
                fit(name, BODY_W - 140)
                set_text(right, row[2])
                fit(right, 100)
            else:
                set_text(tick, "")
                set_text(name, "")
                set_text(right, "")
        if 0 <= cursor - top < self.ROWS:
            self.highlight.x = BODY_X
            self.highlight.y = BODY_Y + (cursor - top) * self.ROW_H
        else:
            self.highlight.x = OFFSCREEN
        if total > self.ROWS:
            track = self.ROWS * self.ROW_H
            self.thumb.height = max(10, track * self.ROWS // total)
            self.thumb.y = BODY_Y + (track - self.thumb.height) * top // (total - self.ROWS)
        else:
            self.thumb.y = OFFSCREEN


SCREENS = {
    state.HOME: HomeScreen,
    state.LIST: ListScreen,
    state.DETAIL: DetailScreen,
    state.EVOLUTION: EvolutionScreen,
    state.SEARCH: SearchScreen,
    state.SETTINGS: SettingsScreen,
    state.QUIZ: QuizScreen,
    state.BROWSE: BrowseScreen,
}


class BatteryIcon:
    """A small battery at the right of the header, drawn over every screen."""

    X = W - 36
    WIDTH, HEIGHT = 22, 12
    INNER = WIDTH - 4

    def __init__(self):
        self.group = displayio.Group()
        y = HEADER_H // 2 - self.HEIGHT // 2
        self.outline = (
            rect(self.group, self.X, y, self.WIDTH, self.HEIGHT, theme.WHITE),
            rect(self.group, self.X + self.WIDTH, y + 3, 2, self.HEIGHT - 6, theme.WHITE),  # nub
        )
        rect(self.group, self.X + 1, y + 1, self.WIDTH - 2, self.HEIGHT - 2, theme.ACCENT)
        self.level = rect(self.group, self.X + 2, y + 2, self.INNER, self.HEIGHT - 4, theme.WHITE)
        self.group.hidden = True
        self._shown = None

    def show(self, volts):
        """Draw the level; None hides the icon (no reading yet)."""
        if volts is None:
            self.group.hidden = True
            return
        width = max(1, round(self.INNER * battery.fraction(volts)))
        color = theme.LOW_BATTERY if battery.is_low(volts) else theme.WHITE
        if (width, color) == self._shown:
            return
        self._shown = (width, color)
        self.level.width = width
        for shape in (self.level, *self.outline):  # all yellow when low, so it stands out
            shape.pixel_shader = palette(color)
        self.group.hidden = False


class UI:
    def __init__(self, display, fonts, records):
        self.display = display
        self.fonts = fonts
        self.records = records
        self.notice = ""
        """A message under the settings, e.g. when they couldn't be saved."""
        self._view = None
        self._screen = None
        self.shiny = False
        """Show shiny pictures (the setting), where the card has them."""
        self.battery = BatteryIcon()
        self._root = displayio.Group()
        """The current screen, with the battery icon on top."""
        self.display.root_group = self._root

    def _set_screen(self, group):
        while len(self._root):
            self._root.pop()
        self._root.append(group)
        self._root.append(self.battery.group)

    def picture(self, folder, pokemon_id):
        """A picture's path on the card: the shiny one when that's on and the card has it."""
        if self.shiny:
            path = self.records.existing("shiny/" + folder, pokemon_id, "bmp")
            if path:
                return path
        return self.records.file(folder, pokemon_id, "bmp")

    def splash(self):
        """The start-up screen, shown while the jingle plays."""
        self._view = None
        group = displayio.Group()
        rect(group, 0, 0, W, H, theme.ACCENT)
        cx, cy = W // 2, H // 2 - 24
        circle(group, cx, cy, 52, theme.WHITE)
        circle(group, cx, cy, 44, theme.LENS)
        circle(group, cx - 16, cy - 16, 10, theme.WHITE)  # the lens's shine
        text(group, self.fonts.title, "POKÉDEX", theme.TEXT, cx, cy + 82, (0.5, 0.5))
        self._set_screen(group)

    def show(self, st):
        """Draw the state: build the screen if the view changed, then update it."""
        self.shiny = st.settings.shiny
        empty = st.selected is None and st.view in (state.LIST, state.DETAIL, state.EVOLUTION)
        if empty:
            self.message("POKÉDEX", "No Pokémon on the SD card.")
            return
        if st.view != self._view:
            self._screen = None
            gc.collect()
            self._screen = SCREENS[st.view](self, st)
            self._view = st.view
            self._set_screen(self._screen.group)
        self._screen.update(st)

    def message(self, title, body):
        """A full-screen message, e.g. when the SD card is missing."""
        self._view = None
        group = displayio.Group()
        rect(group, 0, 0, W, H, theme.BG)
        header(group, self.fonts, title)
        lines = wrap_text_to_pixels(body, W - 4 * PAD, self.fonts.name)
        text(group, self.fonts.name, "\n".join(lines), theme.TEXT, W // 2, H // 2, (0.5, 0.5))
        self._set_screen(group)
