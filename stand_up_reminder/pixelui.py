"""Pixel widgets: the frame, the sprite clock, the bar, the track, the face.

Each widget draws itself on the art grid with the sprites from `pixels`, and
animates on a fixed frame clock rather than by easing anything. Widgets are
told which frame to show; the windows own the clocks.
"""

from __future__ import annotations

from typing import Optional, Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from . import pixels
from .i18n import _
from .pixels import ART, PALETTE, ap, rgb


SPRITES = pixels.Sprites()

# Frame: an outer edge ring, an inner void ring, then the ink body, with the
# four corners punched out so the card reads as a cut pixel shape.
FRAME_RING = ap(1)
CORNER = ap(2)
CARD_PADDING = ap(4)


def animations_enabled() -> bool:
    """Honour the desktop's reduce-animation setting."""
    settings = Gtk.Settings.get_default()
    if settings is None:  # pragma: no cover - depends on the display
        return True
    return bool(settings.get_property("gtk-enable-animations"))


def paint_frame(
    context,
    width: int,
    height: int,
    ring: str = PALETTE["edge"],
    body: str = PALETTE["ink"],
    inner: str = PALETTE["void"],
) -> None:
    """The window frame: two hard rings, an ink body, four cut corners."""
    context.set_operator(1)  # cairo.OPERATOR_SOURCE — corners must clear
    context.set_source_rgba(0, 0, 0, 0)
    context.paint()
    context.set_source_rgb(*rgb(ring))
    context.rectangle(0, 0, width, height)
    context.fill()
    context.set_source_rgb(*rgb(inner))
    context.rectangle(FRAME_RING, FRAME_RING, width - 2 * FRAME_RING, height - 2 * FRAME_RING)
    context.fill()
    context.set_source_rgb(*rgb(body))
    context.rectangle(
        2 * FRAME_RING, 2 * FRAME_RING, width - 4 * FRAME_RING, height - 4 * FRAME_RING
    )
    context.fill()
    context.set_source_rgba(0, 0, 0, 0)
    for x in (0, width - CORNER):
        for y in (0, height - CORNER):
            context.rectangle(x, y, CORNER, CORNER)
    context.fill()
    context.set_operator(2)  # cairo.OPERATOR_OVER


def use_rgba_visual(window: Gtk.Window) -> None:
    screen = window.get_screen()
    visual = screen.get_rgba_visual() if screen is not None else None
    if visual is not None:
        window.set_visual(visual)
    window.set_app_paintable(True)


def corner_place(area, width, height, gap, pill=None, drop: int = 0):
    """Top left of a card parked in the bottom right corner of `area`.

    Windows are anchored by their top left corner, so a card whose size
    follows its content has to be placed from the size it actually has: a
    card placed from a wider size drifts in from the corner, and one placed
    from a narrower size grows off the screen edge. `pill` is the standing
    pill as (top, bottom, width); it only pushes the card out of its column
    when the two share rows, because a pill parked elsewhere is not in the
    way and a card that steps around it anyway reads as badly aligned.
    """
    left = area.x + area.width - width - gap
    top = area.y + area.height - height - gap
    if pill is not None:
        pill_top, pill_bottom, pill_width = pill
        if pill_top < top + height and pill_bottom > top:
            left -= pill_width + gap
    return left, top + drop


def keep_in_corner(window: Gtk.Window, place) -> None:
    """Place the window again whenever its own size changes under it."""
    placed = [None]

    def on_allocate(_widget, _allocation) -> None:
        size = tuple(window.get_size())
        if window.get_visible() and size != placed[0]:
            placed[0] = size
            place()

    window.connect("size-allocate", on_allocate)


class PixelFrameWindow:
    """Mixin giving a window the pixel frame and its cut corners."""

    ring_color = PALETTE["edge"]
    body_color = PALETTE["ink"]

    def setup_frame(self) -> None:
        use_rgba_visual(self)
        self.connect("draw", self._on_frame_draw)

    def set_frame_colors(self, ring: str = "", body: str = "") -> None:
        """Recolour the frame, for windows that carry their own accent."""
        if ring:
            self.ring_color = ring
        if body:
            self.body_color = body
        self.queue_draw()

    def _on_frame_draw(self, _widget, context) -> bool:
        paint_frame(
            context,
            self.get_allocated_width(),
            self.get_allocated_height(),
            self.ring_color,
            self.body_color,
        )
        return False


class Countdown(Gtk.DrawingArea):
    """The clock: big sprite digits, a blinking colon, an urgent shudder."""

    SCALE = 2 * ART  # BIG digits at 2× art scale — 48 × 80 real per glyph

    def __init__(self) -> None:
        super().__init__()
        self._text = "00:00"
        self._color = PALETTE["bone"]
        self._colon = True
        self._shudder = 0
        self.set_size_request(-1, ap(20))
        self.connect("draw", self._on_draw)

    def set_time(self, text: str, color: str, colon: bool, shudder: int = 0) -> None:
        if (text, color, colon, shudder) == (
            self._text,
            self._color,
            self._colon,
            self._shudder,
        ):
            return
        self._text, self._color = text, color
        self._colon, self._shudder = colon, shudder
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        shown = self._text if self._colon else self._text.replace(":", " ")
        width = SPRITES.digits_width(self._text, self.SCALE)
        left = (self.get_allocated_width() - width) // 2
        top = (self.get_allocated_height() - 10 * self.SCALE) // 2
        SPRITES.digits(
            context, shown, left, top + self._shudder * ART, self.SCALE, self._color
        )
        return False


class CellBar(Gtk.DrawingArea):
    """The progress bar: 27 cells that die one at a time, from the right."""

    CELL_WIDTH = ap(3)
    CELL_HEIGHT = ap(4)
    GUTTER = ART

    def __init__(self) -> None:
        super().__init__()
        self._filled = pixels.PROGRESS_CELLS
        self._urgent = False
        self._flipped = 0
        self._accent = PALETTE["amber"]
        self._dying: Optional[tuple[int, int]] = None
        self.set_size_request(-1, self.CELL_HEIGHT)
        self.connect("draw", self._on_draw)

    def set_filled(self, filled: int, animate: bool = True) -> None:
        filled = max(0, min(pixels.PROGRESS_CELLS, filled))
        if filled == self._filled:
            return
        if animate and filled < self._filled:
            self._dying = (filled, 0)
            GLib.timeout_add(40, self._advance_dying)
        self._filled = filled
        was_urgent = self._urgent
        self._urgent = pixels.cells_urgent(filled)
        if self._urgent and not was_urgent:
            self._start_urgency_flip(filled)
        elif not self._urgent:
            self._flipped = 0
        self.queue_draw()

    def set_accent(self, color: str) -> None:
        """Colour the live cells, for a bar that belongs to its own card."""
        if color == self._accent:
            return
        self._accent = color
        self.queue_draw()

    def _start_urgency_flip(self, filled: int) -> None:
        """The survivors turn coral one at a time, from the left."""
        if not animations_enabled():
            self._flipped = pixels.PROGRESS_CELLS
            return
        self._flipped = 0

        def step() -> bool:
            self._flipped += 1
            self.queue_draw()
            return (
                GLib.SOURCE_CONTINUE if self._flipped < filled else GLib.SOURCE_REMOVE
            )

        GLib.timeout_add(60, step)

    def _advance_dying(self) -> bool:
        if self._dying is None:
            return GLib.SOURCE_REMOVE
        cell, frame = self._dying
        if frame >= 2:
            self._dying = None
            self.queue_draw()
            return GLib.SOURCE_REMOVE
        self._dying = (cell, frame + 1)
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _on_draw(self, _area, context) -> bool:
        for index in range(pixels.PROGRESS_CELLS):
            if self._dying is not None and index == self._dying[0]:
                color = (self._accent, PALETTE["bone"], PALETTE["slate"])[
                    self._dying[1]
                ]
            elif index < self._filled:
                flipped = self._urgent and index < self._flipped
                color = PALETTE["coral"] if flipped else self._accent
            else:
                color = PALETTE["slate"]
            context.set_source_rgb(*rgb(color))
            context.rectangle(
                index * (self.CELL_WIDTH + self.GUTTER),
                0,
                self.CELL_WIDTH,
                self.CELL_HEIGHT,
            )
            context.fill()
        return False


class DayTrack(Gtk.DrawingArea):
    """The day timeline: one mark per outcome, placed by time of day."""

    def __init__(self, height_ap: int = 4) -> None:
        super().__init__()
        self._points: list[tuple[float, str]] = []
        self._now: Optional[float] = None
        self._height_ap = height_ap
        self.set_size_request(-1, ap(height_ap) + 2 * FRAME_RING)
        self.connect("draw", self._on_draw)

    def set_points(
        self, points: Sequence[tuple[float, str]], now: Optional[float] = None
    ) -> None:
        self._points = list(points)
        self._now = now
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        context.set_source_rgb(*rgb(PALETTE["slate"]))
        context.rectangle(0, 0, width, height)
        context.fill()
        context.set_source_rgb(*rgb(PALETTE["void"]))
        context.rectangle(
            FRAME_RING, FRAME_RING, width - 2 * FRAME_RING, height - 2 * FRAME_RING
        )
        context.fill()
        track_ap = max(1, (width - 2 * FRAME_RING) // ART)
        for at, outcome in pixels.timeline_marks(self._points, track_ap):
            context.set_source_rgb(*rgb(pixels.MARK_COLORS[outcome]))
            context.rectangle(
                FRAME_RING + ap(at), FRAME_RING, ap(2), height - 2 * FRAME_RING
            )
            context.fill()
        if self._now is not None:
            context.set_source_rgb(*rgb(PALETTE["bone"]))
            context.rectangle(
                FRAME_RING + ap(int(self._now * max(0, track_ap - 1))), 0, ART, height
            )
            context.fill()
        return False


class Face(Gtk.DrawingArea):
    """The character: a disc in the state colour with its features knocked out."""

    def __init__(self, scale: int = 2 * ART, sheet: str = "face") -> None:
        super().__init__()
        self._scale = scale
        self._sheet = sheet
        self._expression = "rest"
        self._color = PALETTE["amber"]
        side = (8 if sheet == "face-bob" else 16) * scale
        self.set_size_request(side, side)
        self.connect("draw", self._on_draw)

    def set_face(self, expression: str, color: str) -> None:
        if (expression, color) == (self._expression, self._color):
            return
        self._expression, self._color = expression, color
        self.queue_draw()

    def play_grin(self, hold: str = "rest") -> None:
        """Six frames of grin, then the expression the state calls for.

        A confirmed break falls back to rest; a week worth grinning about
        keeps the grin, because that is its resting face.
        """
        if not animations_enabled():
            self.set_face("grin2", PALETTE["mint"])
            GLib.timeout_add(
                300, lambda: (self.set_face(hold, PALETTE["mint"]), False)[1]
            )
            return
        frames = ["grin1", "grin2", "grin1", "grin2", "grin1", hold]

        def step() -> bool:
            self.set_face(frames.pop(0), PALETTE["mint"])
            return GLib.SOURCE_CONTINUE if frames else GLib.SOURCE_REMOVE

        step()
        GLib.timeout_add(120, step)

    def _on_draw(self, _area, context) -> bool:
        SPRITES.face(context, 0, 0, self._scale, self._color, self._expression, self._sheet)
        return False



class ScoreLine(Gtk.DrawingArea):
    """The face and the day's scores, drawn together on one line.

    Boxes align on the line box, not on the glyphs, and Silkscreen leaves so
    much room above its letters that a face aligned that way floats. Drawing
    both here puts the middle of the face on the middle of the letters.
    """

    FONT = "Silkscreen 16px"
    GAP = ap(2)

    def __init__(self, scale: int = 2, sheet: str = "face-bob") -> None:
        super().__init__()
        self._scale = scale
        self._sheet = sheet
        self._side = (8 if sheet == "face-bob" else 16) * scale
        self._text = ""
        self._expression = "rest"
        self._face_color = PALETTE["mist"]
        self._text_color = PALETTE["mist"]
        self.set_size_request(-1, self._side)
        self.connect("draw", self._on_draw)

    def set_line(self, text: str, expression: str, color: str) -> None:
        if (text, expression, color) == (
            self._text,
            self._expression,
            self._face_color,
        ):
            return
        self._text, self._expression, self._face_color = text, expression, color
        self.queue_draw()

    def _layout(self):
        layout = self.create_pango_layout(self._text)
        layout.set_font_description(Pango.FontDescription(self.FONT))
        attributes = Pango.AttrList()
        attributes.insert(Pango.attr_letter_spacing_new(Pango.SCALE))
        layout.set_attributes(attributes)
        return layout

    def _on_draw(self, _area, context) -> bool:
        layout = self._layout()
        ink, logical = layout.get_pixel_extents()
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        total = self._side + self.GAP + logical.width
        left = max(0, (width - total) // 2)
        middle = height / 2
        SPRITES.face(
            context,
            left,
            int(middle - self._side / 2),
            self._scale,
            self._face_color,
            self._expression,
            self._sheet,
        )
        context.set_source_rgb(*rgb(self._text_color))
        context.move_to(
            left + self._side + self.GAP,
            middle - (ink.y + ink.height / 2),
        )
        PangoCairo.show_layout(context, layout)
        return False


class SpriteDigits(Gtk.DrawingArea):
    """A run of sprite digits, drawn small for the pill and the tooltip."""

    def __init__(self, scale: int = ART, big: bool = False) -> None:
        super().__init__()
        self._scale = scale
        self._big = big
        self._text = ""
        self._color = PALETTE["bone"]
        self.set_size_request(-1, (10 if big else 7) * scale)
        self.connect("draw", self._on_draw)

    def set_text(self, text: str, color: Optional[str] = None) -> None:
        color = color or self._color
        if (text, color) == (self._text, self._color):
            return
        self._text, self._color = text, color
        self.set_size_request(
            SPRITES.digits_width(text, self._scale, self._big),
            (10 if self._big else 7) * self._scale,
        )
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        width = SPRITES.digits_width(self._text, self._scale, self._big)
        left = max(0, (self.get_allocated_width() - width) // 2)
        SPRITES.digits(
            context, self._text, left, 0, self._scale, self._color, self._big
        )
        return False


class PercentMark(Gtk.DrawingArea):
    """The per-cent sign, drawn on the art grid beside the sprite digits.

    Silkscreen's own glyph collapses at display size, so the score screen
    draws its mark the way it draws every other display glyph: two square
    dots and a hard diagonal, on the same 6 × 10 body as the digits.
    """

    def __init__(self, scale: int) -> None:
        super().__init__()
        self._scale = scale
        self._color = PALETTE["bone"]
        self.set_size_request(6 * scale, 10 * scale)
        self.set_valign(Gtk.Align.END)
        self.connect("draw", self._on_draw)

    def set_color(self, color: str) -> None:
        if color == self._color:
            return
        self._color = color
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        context.set_source_rgb(*rgb(self._color))
        for x, y in ((0, 0), (1, 0), (0, 1), (1, 1), (4, 8), (5, 8), (4, 9), (5, 9)):
            context.rectangle(x * self._scale, y * self._scale, self._scale, self._scale)
        for y in range(10):
            x = round((9 - y) * 5 / 9)
            context.rectangle(x * self._scale, y * self._scale, self._scale, self._scale)
        context.fill()
        return False


class Burst(Gtk.DrawingArea):
    """The five-frame mint burst that plays once when a break is confirmed."""

    def __init__(self, scale: int = ART) -> None:
        super().__init__()
        self._scale = scale
        self._frame: Optional[int] = None
        self._timer = 0
        self.set_size_request(12 * scale, 12 * scale)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_no_show_all(True)
        self.connect("draw", self._on_draw)

    def play(self, done=None) -> None:
        if not animations_enabled():
            if done is not None:
                GLib.timeout_add(300, lambda: (done(), GLib.SOURCE_REMOVE)[1])
            return
        self._frame = 0
        self._done = done
        self.show()
        self.queue_draw()
        self._timer = GLib.timeout_add(60, self._advance)

    def _advance(self) -> bool:
        if self._frame is None:
            return GLib.SOURCE_REMOVE
        self._frame += 1
        if self._frame > 4:
            self._frame = None
            self._timer = 0
            self.hide()
            if getattr(self, "_done", None) is not None:
                self._done()
            return GLib.SOURCE_REMOVE
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _on_draw(self, _area, context) -> bool:
        if self._frame is None:
            return False
        SPRITES.paint(
            context, "burst", 0, 0, self._scale, PALETTE["mint"], frame=self._frame
        )
        return False


class WipeOverlay(Gtk.DrawingArea):
    """Reveals a card in six bands from the centre out, 40 ms apart."""

    BANDS = 6

    def __init__(self) -> None:
        super().__init__()
        self._hidden: set[int] = set()
        self.set_no_show_all(True)
        self.connect("draw", self._on_draw)

    def play(self) -> None:
        if not animations_enabled():
            self._hidden = set()
            self.hide()
            return
        self._hidden = set(range(self.BANDS))
        order = list(pixels.WIPE_ORDER)
        self.show()
        self.queue_draw()

        def step() -> bool:
            self._hidden.discard(order.pop(0))
            self.queue_draw()
            if order:
                return GLib.SOURCE_CONTINUE
            self.hide()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(40, step)

    def _on_draw(self, _area, context) -> bool:
        if not self._hidden:
            return False
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        band = height / self.BANDS
        context.set_source_rgb(*rgb(PALETTE["ink"]))
        for index in self._hidden:
            context.rectangle(0, int(index * band), width, int(band) + 1)
        context.fill()
        return False



def pixel_button(
    label: str,
    variant: str = "default",
    glyph: str = "",
    glyph_color: str = "",
) -> Gtk.Button:
    """A flat pixel button; the variant carries its palette role.

    A glyph sits to the left of the label with the text still centred in what
    is left, so a column of buttons keeps one line of icons down its edge and
    reads as a list rather than as decorated prose.
    """
    button = Gtk.Button()
    button.get_style_context().add_class("pixel-button")
    button.get_style_context().add_class(f"pixel-button-{variant}")
    button.set_can_focus(True)
    if not glyph:
        button.set_label(label)
        return button
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    mark = GlyphMark(glyph, glyph_color or PALETTE["mist"], scale=3)
    mark.set_margin_end(ap(2))
    row.pack_start(mark, False, False, 0)
    text = Gtk.Label(label=label)
    text.set_hexpand(True)
    row.pack_start(text, True, True, 0)
    button.add(row)
    # Gtk.Button.set_label would throw this whole row away and put a bare
    # label in its place, taking the glyph with it. Callers that relabel go
    # through set_button_label instead, which finds this.
    button.pixel_text = text
    return button


def set_button_label(button: Gtk.Button, label: str) -> None:
    """Relabel a pixel button without discarding the glyph beside its text."""
    text = getattr(button, "pixel_text", None)
    if text is None:
        button.set_label(label)
    else:
        text.set_text(label)


# Settings icons, authored as pixels rather than shipped as art. Each is seven
# art pixels square, which is the smallest grid that still reads as a shape at
# a glance — the whole reason they are here is to be found without reading.
GLYPHS = {
    "clock": (
        "..###..",
        ".#...#.",
        "#..#..#",
        "#..##.#",
        "#.....#",
        ".#...#.",
        "..###..",
    ),
    "cup": (
        ".......",
        "######.",
        "#....#.",
        "#....##",
        "#....#.",
        ".####..",
        ".......",
    ),
    "chart": (
        ".......",
        ".....#.",
        "...#.#.",
        "...#.#.",
        ".#.#.#.",
        ".#.#.#.",
        "#######",
    ),
    "cursor": (
        "#......",
        "##.....",
        "###....",
        "####...",
        "#####..",
        "##.##..",
        "....##.",
    ),
    "door": (
        "#####..",
        "#...#..",
        "#...#..",
        "#..##..",
        "#...#..",
        "#...#..",
        "#####..",
    ),
    "topbar": (
        "#######",
        "#######",
        ".......",
        "#.....#",
        "#.....#",
        "#.....#",
        "#######",
    ),
    "eye": (
        ".......",
        ".#####.",
        "#..#..#",
        "#.###.#",
        "#..#..#",
        ".#####.",
        ".......",
    ),
    "window": (
        "#######",
        "#..#..#",
        "#..#..#",
        "#######",
        "#..#..#",
        "#..#..#",
        "#######",
    ),
    "eyeshut": (
        ".......",
        ".......",
        ".#####.",
        "#######",
        ".#...#.",
        ".......",
        ".......",
    ),
    "arrows": (
        ".......",
        "..#.#..",
        ".##.##.",
        "#######",
        ".##.##.",
        "..#.#..",
        ".......",
    ),
    "speaker": (
        "...##..",
        "..###..",
        "###.#.#",
        "###.#..",
        "###.#.#",
        "..###..",
        "...##..",
    ),
    "note": (
        "....##.",
        "....##.",
        "...###.",
        "...#.#.",
        ".###.#.",
        ".###...",
        ".#.....",
    ),
    "back": (
        "...#...",
        "..##...",
        ".###...",
        "..##..#",
        "...#..#",
        "......#",
        ".#####.",
    ),
    "stand": (
        "..##...",
        "..##...",
        ".####..",
        "#.##.#.",
        "..##...",
        ".#..#..",
        ".#..#..",
    ),
    "pause": (
        ".##.##.",
        ".##.##.",
        ".##.##.",
        ".##.##.",
        ".##.##.",
        ".##.##.",
        ".......",
    ),
    "play": (
        ".#.....",
        ".###...",
        ".#####.",
        ".######",
        ".#####.",
        ".###...",
        ".#.....",
    ),
    "sliders": (
        ".#...#.",
        ".#...#.",
        "###..#.",
        ".#...#.",
        ".#..###",
        ".#...#.",
        ".#...#.",
    ),
    "power": (
        "...#...",
        ".#.#.#.",
        "#..#..#",
        "#..#..#",
        "#.....#",
        ".#...#.",
        "..###..",
    ),
    "hourglass": (
        "#######",
        ".#####.",
        "..###..",
        "...#...",
        "..###..",
        ".#####.",
        "#######",
    ),
}
GLYPH_SIZE = 7


class GlyphMark(Gtk.DrawingArea):
    """One settings icon, painted from its pixel table in a single colour."""

    def __init__(self, name: str, color: str = PALETTE["mist"], scale: int = ART):
        super().__init__()
        self._rows = GLYPHS[name]
        self._color = color
        self._scale = scale
        self.set_size_request(GLYPH_SIZE * scale, GLYPH_SIZE * scale)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._on_draw)

    def set_color(self, color: str) -> None:
        if color == self._color:
            return
        self._color = color
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        context.set_source_rgb(*rgb(self._color))
        for y, row in enumerate(self._rows):
            for x, cell in enumerate(row):
                if cell != ".":
                    context.rectangle(
                        x * self._scale, y * self._scale, self._scale, self._scale
                    )
        context.fill()
        return False


class FoldMark(Gtk.DrawingArea):
    """A hard pixel triangle: pointing right when shut, down when open."""

    def __init__(self, is_open: bool = False, scale: int = ART) -> None:
        super().__init__()
        self._scale = scale
        self._open = bool(is_open)
        self._color = PALETTE["mist"]
        self.set_size_request(6 * scale, 6 * scale)
        self.connect("draw", self._on_draw)

    def set_open(self, is_open: bool) -> None:
        if bool(is_open) == self._open:
            return
        self._open = bool(is_open)
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        context.set_source_rgb(*rgb(self._color))
        for step in range(3):
            if self._open:
                # A wedge narrowing downward: 5 wide, then 3, then 1.
                context.rectangle(
                    (1 + step) * self._scale,
                    (2 + step) * self._scale,
                    (5 - 2 * step) * self._scale,
                    self._scale,
                )
            else:
                context.rectangle(
                    (2 + step) * self._scale,
                    (1 + step) * self._scale,
                    self._scale,
                    (5 - 2 * step) * self._scale,
                )
        context.fill()
        return False


class CloseMark(Gtk.DrawingArea):
    """The window's close mark: a hard pixel cross, drawn on the art grid."""

    def __init__(self, scale: int = ART) -> None:
        super().__init__()
        self._scale = scale
        self._color = PALETTE["mist"]
        self.set_size_request(6 * scale, 6 * scale)
        self.connect("draw", self._on_draw)

    def set_color(self, color: str) -> None:
        if color == self._color:
            return
        self._color = color
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        context.set_source_rgb(*rgb(self._color))
        for step in range(6):
            context.rectangle(
                step * self._scale, step * self._scale, self._scale, self._scale
            )
            context.rectangle(
                (5 - step) * self._scale, step * self._scale, self._scale, self._scale
            )
        context.fill()
        return False


def page_header(title: str, on_close) -> Gtk.Box:
    """A page's title, with its close mark in the top corner."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    label = pixel_label(title, "pixel-window-title", 0.0)
    label.set_hexpand(True)
    row.pack_start(label, True, True, 0)

    button = Gtk.Button()
    button.get_style_context().add_class("pixel-check")
    button.set_relief(Gtk.ReliefStyle.NONE)
    button.set_valign(Gtk.Align.START)
    button.set_tooltip_text(_("Close"))
    mark = CloseMark()
    button.add(mark)
    button.connect("clicked", on_close)
    button.connect("enter-notify-event", lambda *_a: mark.set_color(PALETTE["coral"]))
    button.connect("leave-notify-event", lambda *_a: mark.set_color(PALETTE["mist"]))
    row.pack_end(button, False, False, 0)
    return row


def pixel_label(text: str, style: str, align: float = 0.5) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_xalign(align)
    label.get_style_context().add_class(style)
    return label


def page_window(window: Gtk.Window) -> None:
    """A page of the application: undecorated, above the desk, still a window.

    Pages stay above the windows you were already working in — losing one
    behind a maximised browser reads as having closed it — but they never
    fight each other: opening one raises it over the others. They are
    dragged by their own body, since they carry no title bar to grab.
    """
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_keep_above(True)
    window.set_type_hint(Gdk.WindowTypeHint.NORMAL)
    window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    window.connect("button-press-event", _begin_drag)


def raise_page(window: Gtk.Window) -> None:
    """Show a page and put it in front, even of the app's other pages.

    A page that has only just been mapped is not stacked until the server
    has caught up, so the request is repeated on the next turn of the loop;
    without that, opening a page from the top-bar menu left it behind the
    page that was already open.
    """
    window.show_all()
    window.deiconify()
    window.present()
    GLib.timeout_add(50, lambda: (window.present(), GLib.SOURCE_REMOVE)[1])


def _begin_drag(window: Gtk.Window, event) -> bool:
    if event.button != 1:
        return False
    window.begin_move_drag(
        event.button, int(event.x_root), int(event.y_root), event.time
    )
    return True


def keep_above(window: Gtk.Window) -> None:
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_keep_above(True)
    window.set_skip_taskbar_hint(True)
    window.set_skip_pager_hint(True)
    window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
    window.stick()
