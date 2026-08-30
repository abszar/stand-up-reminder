"""The eye-break card: a small popup that asks for twenty seconds and leaves.

It is the quietest surface in the application on purpose. It dims nothing,
takes no focus and closes itself, because it arrives three times an hour and
anything that has to be dismissed at that rate stops being read. Everything
it draws is on the same four-pixel art grid as the rest of the interface.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk

from . import eyes
from . import pixels
from . import pixelui as ui
from .i18n import _
from .pixels import ART, PALETTE, ap


# The card is drawn on a canvas of art pixels and scaled up whole, so every
# edge lands on the grid however the window is sized.
CANVAS_W = 64
CANVAS_H = 38
FRAME_MS = 40

# One eye, thirteen art pixels across and nine down: a run per row.
EYE_ROWS = (
    (4, 8), (2, 10), (1, 11), (0, 12), (0, 12), (0, 12), (1, 11), (2, 10), (4, 8),
)

# Two hills behind the window. The far one is drawn in edge rather than mint
# so that distance reads as haze, which is the whole point of the card.
FAR_HILL = (3, 4, 4, 5, 6, 6, 5, 4, 4, 3, 3, 4, 5, 6, 7, 7,
            6, 5, 4, 4, 3, 3, 4, 5, 5, 4, 4, 3, 3, 4, 4, 3)
NEAR_HILL = (2, 2, 3, 4, 4, 3, 3, 2, 2, 3, 4, 5, 5, 4, 3, 3,
             2, 2, 3, 3, 4, 4, 5, 4, 3, 3, 2, 2, 3, 4, 4, 3)

# The ring the moving-eye card asks you to walk, and the eyes at its middle.
RING_X, RING_Y = 32, 19
RING_RX, RING_RY = 27, 16


def _fill(context, color: str, x: int, y: int, width: int, height: int) -> None:
    context.set_source_rgb(*pixels.rgb(color))
    context.rectangle(x, y, width, height)
    context.fill()


def _eye(context, ox: int, oy: int, accent: str, body: str, gaze, lid: float) -> None:
    """One eye, drawn a pixel at a time so the iris never spills past the lid."""
    for row, (start, end) in enumerate(EYE_ROWS):
        for x in range(start, end + 1):
            dx = x - (6 + gaze[0])
            dy = row - (4 + gaze[1])
            color = "bone"
            if abs(dx) <= 2 and abs(dy) <= 2:
                color = accent
            if abs(dx) <= 1 and abs(dy) <= 1:
                color = "void"
            _fill(context, PALETTE[color], ox + x, oy + row, 1, 1)
    closed = round(lid * 4)
    for step in range(closed):
        for row in (step, 8 - step):
            start, end = EYE_ROWS[row]
            _fill(context, PALETTE[body], ox + start, oy + row, end - start + 1, 1)
    if lid > 0.95:
        _fill(context, PALETTE[accent], ox, oy + 4, 13, 1)
    elif closed:
        start, end = EYE_ROWS[closed]
        _fill(context, PALETTE[accent], ox + start, oy + closed, end - start + 1, 1)


def _pair(context, centre: int, oy: int, accent: str, body: str, gaze, lid=0.0) -> None:
    _eye(context, centre - 15, oy, accent, body, gaze, lid)
    _eye(context, centre + 2, oy, accent, body, gaze, lid)


def _shut_eye(context, ox: int, oy: int, tight: bool, outward: int) -> None:
    """A shut eye reads as squeezed or resting, and they must not be confused."""
    plum = PALETTE["plum"]
    if tight:
        _fill(context, plum, ox + 1, oy + 3, 11, 2)
        corner = ox + 12 if outward > 0 else ox
        for step in range(1, 4):
            _fill(context, plum, corner + outward * step, oy + 3 - step, 1, 1)
            _fill(context, plum, corner + outward * step, oy + 4 + step, 1, 1)
    else:
        _fill(context, plum, ox, oy + 4, 13, 1)
        _fill(context, plum, ox + 2, oy + 5, 9, 1)


def _window(context, ox: int, oy: int, ms: int) -> None:
    """A window with something living behind it — the card's whole argument."""
    width, height = 34, 24
    _fill(context, PALETTE["edge"], ox, oy, width, height)
    ix, iy = ox + 1, oy + 1
    _fill(context, PALETTE["sky"], ix, iy, 32, 13)
    for column in range(32):
        far = FAR_HILL[column]
        near = NEAR_HILL[column]
        _fill(context, PALETTE["edge"], ix + column, iy + 13 - far, 1, far + 3)
        _fill(context, PALETTE["mint"], ix + column, iy + 16 - near, 1, near + 4)
    _fill(context, pixels.HEAT_SHADES[0], ix, iy + 20, 32, 2)

    sun = PALETTE["amber"] if eyes.sun_lit(ms) else PALETTE["bone"]
    _fill(context, sun, ix + 24, iy + 2, 4, 4)
    _fill(context, PALETTE["bone"], ix + 25, iy + 3, 1, 1)

    for row, span, direction in ((4, 7, 1), (8, 5, -1)):
        left = eyes.cloud_offset(ms, direction)
        _fill(context, PALETTE["bone"], ix + left, iy + row, span, 1)
        _fill(context, PALETTE["bone"], ix + left + 1, iy + row - 1, span - 2, 1)

    bird = eyes.bird_x(ms)
    if bird is not None:
        by = iy + 6 + (ms // 200) % 2
        for dx, dy in ((0, 0), (2, 0), (1, 1)):
            _fill(context, PALETTE["ink"], ix + bird + dx, by + dy, 1, 1)

    edge = PALETTE["edge"]
    _fill(context, edge, ox, oy, width, 1)
    _fill(context, edge, ox, oy + height - 1, width, 1)
    _fill(context, edge, ox, oy, 1, height)
    _fill(context, edge, ox + width - 1, oy, 1, height)
    _fill(context, edge, ox + 16, oy, 1, height)
    _fill(context, edge, ox, oy + 11, width, 1)


def _station(name: str):
    gaze = eyes.GAZE[name]
    sign = lambda value: (value > 0) - (value < 0)  # noqa: E731 - one line, one job
    return RING_X + sign(gaze[0]) * RING_RX, RING_Y + sign(gaze[1]) * RING_RY


class EyeCanvas(Gtk.DrawingArea):
    """The moving part of the card, one painter per prompt."""

    def __init__(self) -> None:
        super().__init__()
        self._prompt = eyes.LOOK_FAR
        self._ms = 0
        self.set_size_request(CANVAS_W * ART, CANVAS_H * ART)
        self.connect("draw", self._on_draw)

    def set_frame(self, prompt, ms: int) -> None:
        self._prompt = prompt
        self._ms = ms
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        context.save()
        context.scale(ART, ART)
        _fill(context, PALETTE[self._prompt.body], 0, 0, CANVAS_W, CANVAS_H)
        painter = {
            "far": self._paint_far,
            "shut": self._paint_shut,
            "move": self._paint_move,
        }[self._prompt.key]
        painter(context, self._ms)
        context.restore()
        return False

    def _paint_far(self, context, ms: int) -> None:
        # The window is the thing being looked at, so it sits above the eyes
        # rather than beside them, and they look up into it.
        _window(context, 15, 1, ms)
        gaze = (0, 0) if ms < 600 else (0, -2)
        _pair(context, 32, 28, "sky", self._prompt.body, gaze)

    def _paint_shut(self, context, ms: int) -> None:
        frame = eyes.shut_frame(ms)
        if frame.lid < 0.95:
            _pair(context, 32, 14, "plum", self._prompt.body, (0, 0), frame.lid)
        else:
            _shut_eye(context, 17, 14, frame.tight, -1)
            _shut_eye(context, 34, 14, frame.tight, 1)
        for index in range(3):
            lit = PALETTE["plum"] if index < frame.pips else PALETTE["slate"]
            _fill(context, lit, 26 + index * 6, 30, 4, 2)

    def _paint_move(self, context, ms: int) -> None:
        name = eyes.move_station(ms)
        slate = PALETTE["slate"]
        for x in range(RING_X - RING_RX, RING_X + RING_RX + 1, 3):
            _fill(context, slate, x, RING_Y - RING_RY, 1, 1)
            _fill(context, slate, x, RING_Y + RING_RY, 1, 1)
        for y in range(RING_Y - RING_RY, RING_Y + RING_RY + 1, 3):
            _fill(context, slate, RING_X - RING_RX, y, 1, 1)
            _fill(context, slate, RING_X + RING_RX, y, 1, 1)
        for other in eyes.STATIONS:
            x, y = _station(other)
            if other == name:
                _fill(context, PALETTE["mint"], x - 2, y - 2, 4, 4)
            else:
                _fill(context, PALETTE["edge"], x - 1, y - 1, 2, 2)
        _pair(context, RING_X, RING_Y - 4, "mint", self._prompt.body, eyes.GAZE[name])


class EyeWindow(Gtk.Window, ui.PixelFrameWindow):
    """The card itself: twenty seconds, then it closes on its own."""

    WIDTH = ap(72)

    def __init__(self, on_squeeze, on_finished) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=_("Eye break"))
        self._on_squeeze = on_squeeze
        self._on_finished = on_finished
        self._prompt = eyes.LOOK_FAR
        self._ms = 0
        self._timer = 0
        self._squeezed = 0
        self._started = 0
        self.set_default_size(self.WIDTH, -1)
        self.set_size_request(self.WIDTH, -1)
        self.set_resizable(False)
        self.set_decorated(False)
        # It must not take the keyboard away from whatever is being typed:
        # the card is a suggestion, not an interruption.
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_keep_above(True)
        self.get_style_context().add_class("pixel-window")
        self.setup_frame()
        self.connect("delete-event", lambda *_args: True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", lambda *_args: (self.finish(), True)[1])

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_border_width(ap(2) + ap(3))

        self.title = ui.pixel_label("", "pixel-window-title", 0.0)
        card.pack_start(self.title, False, False, 0)
        self.subtitle = ui.pixel_label("", "pixel-caption", 0.0)
        self.subtitle.set_margin_bottom(ap(3))
        card.pack_start(self.subtitle, False, False, 0)

        self.canvas = EyeCanvas()
        card.pack_start(self.canvas, False, False, 0)

        self.bar = ui.CellBar()
        self.bar.set_margin_top(ap(3))
        self.bar.set_margin_bottom(ap(2))
        card.pack_start(self.bar, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.seconds = ui.SpriteDigits(scale=ART, big=True)
        footer.pack_start(self.seconds, False, False, 0)
        hint = ui.pixel_label(_("CLICK SKIPS"), "pixel-hint", 1.0)
        hint.set_hexpand(True)
        hint.set_valign(Gtk.Align.END)
        footer.pack_start(hint, True, True, 0)
        card.pack_start(footer, False, False, 0)

        self.add(card)

    # --- running -----------------------------------------------------------
    def begin(self, prompt) -> None:
        """Show the card and start its twenty seconds."""
        self._prompt = prompt
        self._ms = 0
        self._squeezed = 0
        # Timed against the clock rather than by counting frames: GLib
        # timeouts drift, and twenty seconds of drift is a second and a bit
        # of a countdown that visibly lags its own digits.
        self._started = GLib.get_monotonic_time()
        self.title.set_markup(
            '<span foreground="%s">%s</span>'
            % (PALETTE[prompt.accent], GLib.markup_escape_text(prompt.title))
        )
        self.subtitle.set_text(prompt.subtitle)
        self.canvas.set_frame(prompt, 0)
        self.bar.set_accent(PALETTE[prompt.accent])
        self.bar.set_filled(pixels.PROGRESS_CELLS, animate=False)
        self.seconds.set_text("%02d" % eyes.CARD_SECONDS, PALETTE["bone"])
        self.set_frame_colors(PALETTE[prompt.accent], PALETTE[prompt.body])
        self.show_all()
        self._place()
        self._stop_timer()
        # Reduced motion still gets the card and its countdown, just without
        # the frames in between.
        period = FRAME_MS if ui.animations_enabled() else 1000
        self._timer = GLib.timeout_add(period, self._advance)

    def finish(self) -> None:
        self._stop_timer()
        self.hide()
        self._on_finished()

    def _stop_timer(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _advance(self) -> bool:
        self._ms = (GLib.get_monotonic_time() - self._started) // 1000
        return self._step()

    def _step(self) -> bool:
        total = eyes.CARD_SECONDS * 1000
        if self._ms >= total:
            self._timer = 0
            self.finish()
            return GLib.SOURCE_REMOVE
        left = total - self._ms
        self.canvas.set_frame(self._prompt, self._ms)
        if self._prompt.key == "shut":
            frame = eyes.shut_frame(self._ms)
            self.subtitle.set_text(frame.phase)
            if frame.pips > self._squeezed:
                self._squeezed = frame.pips
                self._on_squeeze()
        filled = pixels.filled_cells(left / 1000, eyes.CARD_SECONDS)
        self.bar.set_filled(filled)
        urgent = pixels.cells_urgent(filled)
        self.seconds.set_text(
            "%02d" % max(0, -(-left // 1000)),
            PALETTE["coral"] if urgent else PALETTE["bone"],
        )
        return GLib.SOURCE_CONTINUE

    def _place(self) -> None:
        """Bottom right, clear of the standing pill's edge."""
        display = Gdk.Display.get_default()
        if display is None:
            return
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            return
        area = monitor.get_workarea()
        width, height = self.get_size()
        self.move(
            area.x + area.width - width - ap(16),
            area.y + area.height - height - ap(6),
        )
