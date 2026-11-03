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
    ROW_H = 64
    GAP = 8

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
        subtitles = (
            f"{len(st.dex)} entries",
            "Find by name or number",
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
        label = (st.type_filter or "all").upper()
        color = theme.type_color(st.type_filter) if st.type_filter else theme.PANEL_LIGHT
        self.filter.set(label, color)
        self.filter.place(HEADER_RIGHT - text_width(self.count) - 8 - self.filter.width)

        top = max(0, min(st.index - self.ROWS // 2, total - self.ROWS))
        if self._shown != (top, st.type_filter):
            self._shown = (top, st.type_filter)
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

        if st.selected != self._preview_pos:
            self._preview_pos = st.selected
            self._draw_preview(st)
        hints = "▲▼ move  ◀▶ page  A open  L/R type"
        set_text(self.hints, hints + ("  B all" if st.type_filter else ""))

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
        path = self.ui.records.file("spr", pokemon_id, "bmp")
        replace(self.sprite, image(path, *self.sprite_center))
        self.preview_number.text = "#" + number(pokemon_id)
        self.preview_name.text = st.dex.names[pos]
        self.preview_types.set(st.dex.types(pos))


class DetailScreen(Screen):
    FLAVOR_H = 58
    ART = 190
    FLAVOR_LINES = 3

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

        x = BODY_X + art + 2 * PAD
        right = BODY_X + BODY_W
        self.types = TypeBadges(g, fonts.bold, x, BODY_Y + 9)
        self.measures = text(g, fonts.body, "", theme.MUTED, x, BODY_Y + 9)
        rows_top = BODY_Y + 26
        row_h = (BODY_Y + top_h - rows_top) // (len(theme.STAT_LABELS) + 1)
        self.bar_x = x + 84
        self.bar_w = right - self.bar_x
        self.stats = []
        for i, label in enumerate(theme.STAT_LABELS + ("TOTAL",)):
            cy = rows_top + i * row_h + row_h // 2
            text(g, fonts.bold, label, theme.MUTED, x, cy)
            value = text(g, fonts.body, "", theme.TEXT, x + 76, cy, (1, 0.5))
            bar = None
            if i < len(theme.STAT_LABELS):
                rect(g, self.bar_x, cy - 4, self.bar_w, 8, theme.PANEL)
                bar = rect(g, self.bar_x, cy - 4, 1, 8, theme.MUTED)
            self.stats.append((value, bar))

        flavor_y = BODY_Y + BODY_H - self.FLAVOR_H
        rect(g, BODY_X, flavor_y, BODY_W, self.FLAVOR_H, theme.PANEL)
        self.flavor = text(
            g, fonts.body, "", theme.TEXT, BODY_X + 8, flavor_y + 5, (0, 0), line_spacing=1.1
        )
        hints = "◀▶ next  L/R ±10  A evolution  SEL replay  B back"
        self.position = footer(g, fonts, hints)[1]
        self._shown = None

    def update(self, st):
        pokemon_id = st.selected_id
        position = f"{st.index + 1}/{len(st.visible)}"
        set_text(self.position, position if st.settings.sound else "MUTED   " + position)
        if (pokemon_id, st.settings.units) == self._shown:
            return
        self._shown = (pokemon_id, st.settings.units)
        pos = st.selected
        self.title.text = f"#{number(pokemon_id)}  {st.dex.names[pos]}"
        replace(self.art, image(self.ui.records.file("art", pokemon_id, "bmp"), *self.art_center))
        width = self.types.set(st.dex.types(pos))
        self.measures.anchored_position = (self.types.x + width + 10, BODY_Y + 9)

        entry = st.entry
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
            path = self.ui.records.file(f"ev{fitting[0]}", species_id, "bmp")
            picture = image(path, cx, cy)
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
    ROW_H = 34
    GAP = 6

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


SCREENS = {
    state.HOME: HomeScreen,
    state.LIST: ListScreen,
    state.DETAIL: DetailScreen,
    state.EVOLUTION: EvolutionScreen,
    state.SEARCH: SearchScreen,
    state.SETTINGS: SettingsScreen,
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
        self.battery = BatteryIcon()
        self._root = displayio.Group()
        """The current screen, with the battery icon on top."""
        self.display.root_group = self._root

    def _set_screen(self, group):
        while len(self._root):
            self._root.pop()
        self._root.append(group)
        self._root.append(self.battery.group)

    def show(self, st):
        """Draw the state: build the screen if the view changed, then update it."""
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
