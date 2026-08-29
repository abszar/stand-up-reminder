"""Pixel widgets: the frame, the sprite clock, the bar, the track, the face.

Each widget draws itself on the art grid with the sprites from `pixels`, and
animates on a fixed frame clock rather than by easing anything. Widgets are
told which frame to show; the windows own the clocks.
"""

from __future__ import annotations

from typing import Optional, Sequence

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, GLib, Gtk

from . import pixels
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


class PixelFrameWindow:
    """Mixin giving a window the pixel frame and its cut corners."""

    def setup_frame(self) -> None:
        use_rgba_visual(self)
        self.connect("draw", self._on_frame_draw)

    def _on_frame_draw(self, _widget, context) -> bool:
        paint_frame(
            context, self.get_allocated_width(), self.get_allocated_height()
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
                color = (PALETTE["amber"], PALETTE["bone"], PALETTE["slate"])[
                    self._dying[1]
                ]
            elif index < self._filled:
                flipped = self._urgent and index < self._flipped
                color = PALETTE["coral"] if flipped else PALETTE["amber"]
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

    def play_grin(self) -> None:
        """Six frames of grin, then back to rest — the reward face."""
        if not animations_enabled():
            self.set_face("grin2", PALETTE["mint"])
            GLib.timeout_add(
                300, lambda: (self.set_face("rest", PALETTE["mint"]), False)[1]
            )
            return
        frames = ["grin1", "grin2", "grin1", "grin2", "grin1", "rest"]

        def step() -> bool:
            self.set_face(frames.pop(0), PALETTE["mint"])
            return GLib.SOURCE_CONTINUE if frames else GLib.SOURCE_REMOVE

        step()
        GLib.timeout_add(120, step)

    def _on_draw(self, _area, context) -> bool:
        SPRITES.face(context, 0, 0, self._scale, self._color, self._expression, self._sheet)
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



def pixel_button(label: str, variant: str = "default") -> Gtk.Button:
    """A flat pixel button; the variant carries its palette role."""
    button = Gtk.Button(label=label)
    button.get_style_context().add_class("pixel-button")
    button.get_style_context().add_class(f"pixel-button-{variant}")
    button.set_can_focus(True)
    return button


def pixel_label(text: str, style: str, align: float = 0.5) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_xalign(align)
    label.get_style_context().add_class(style)
    return label


def keep_above(window: Gtk.Window) -> None:
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_keep_above(True)
    window.set_skip_taskbar_hint(True)
    window.set_skip_pager_hint(True)
    window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
    window.stick()
