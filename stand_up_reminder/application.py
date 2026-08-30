from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping, Optional, Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3, Gdk, Gio, GLib, Gtk

try:  # Sound cues are optional; the reminder works without them.
    gi.require_version("GSound", "1.0")
    from gi.repository import GSound
except (ImportError, ValueError):  # pragma: no cover - depends on host packages
    GSound = None

from . import eyes
from . import pixels
from . import pixelui as ui
from .eyecard import EyeWindow
from .i18n import _, ngettext
from .pixels import ART, PALETTE, ap
from .scheduler import Phase, Scheduler, TimingMode, Transition
from .settings import (
    BREAK_PRESETS,
    IDLE_CREDIT_PRESETS,
    WORK_PRESETS,
    Settings,
    SettingsStore,
)
from .stats import (
    GRID_DAYS,
    WEEK_DAYS,
    BreakOutcome,
    DailyStats,
    StatsStore,
    adherence_percent,
    aggregate_stats,
    day_tooltip,
    heat_level,
    heatmap_weeks,
    outcome_summary,
    last_days,
    rating_label,
    score_headline,
    score_line,
    summary_label,
    timeline_layout,
    today_key,
    week_label,
)


APP_ID = "io.github.abdelali.StandUpReminder"
APP_NAME = "Stand Up Reminder"
ICON_NAME = "stand-up-reminder-symbolic"
PAUSED_ICON_NAME = "stand-up-reminder-paused-symbolic"
IDLE_POLL_SECONDS = 5
PAUSE_PRESETS = (30 * 60, 60 * 60)
# The standing pill: a figure, its count, and the gap it keeps from the edge.


# The pill sits flush against the right screen edge.
PILL_EDGE_GAP = 0


def sound_dir() -> Path:
    """Where the shipped sound files live, installed or in the tree."""
    override = os.environ.get("STAND_UP_REMINDER_SOUNDS")
    if override:
        return Path(override)
    package = Path(__file__).resolve().parent
    installed = package.parent / "sounds"
    if installed.is_dir():
        return installed
    return package.parent / "data" / "sounds"


def sound_player(which=shutil.which) -> str:
    """A command that can play a shipped WAV where GSound is not installed.

    GSound is an optional dependency and is missing on plenty of desktops, so
    the cues that ship as files fall back to whatever the system already has.
    Cues that name a freedesktop event have no file to fall back to and stay
    silent, which is the right way round: the application's own sounds work
    everywhere, and the desktop's own sounds need the desktop's own library.
    """
    for name in ("paplay", "aplay"):
        found = which(name)
        if found:
            return found
    return ""


@dataclass(frozen=True)
class SoundCue:
    """One sound the application can make, and the name it answers to.

    Playing a sound takes a cue rather than a bare event id, so a sound the
    application does not declare cannot be played at all. Declaring one here
    is what gives it its own row in the settings, which is why a cue added
    later is switchable without anybody remembering to wire it up.

    A cue names exactly one source: a freedesktop event the desktop theme
    supplies, or a file shipped with the application.
    """

    key: str
    label: str
    event_id: str = ""
    filename: str = ""


SOUND_CUES = (
    SoundCue("break_start", _("The break starting"), filename="break-due.wav"),
    SoundCue("break_done", _("The break finishing"), filename="break-over.wav"),
    SoundCue("break_kept", _("A break kept"), filename="break-kept.wav"),
    SoundCue("eye_far", _("Look far"), filename="eye-look-far.wav"),
    SoundCue("eye_shut", _("Close your eyes"), filename="eye-close.wav"),
    SoundCue("eye_move", _("Move your eyes"), filename="eye-move.wav"),
    SoundCue("eye_squeeze", _("Each squeeze"), filename="eye-squeeze.wav"),
    SoundCue("eye_done", _("An eye break ending"), filename="eye-done.wav"),
)
EYE_CUES = {cue.key: cue for cue in SOUND_CUES}


def sound_allowed(settings, cue: SoundCue, discreet: bool = False) -> bool:
    """Whether this cue may be heard: discreet mode, the master, then its own.

    Discreet comes first and answers for every cue at once. It is a lid over
    the settings rather than part of them: nothing the user has configured is
    changed or needs restoring when it comes off.
    """
    if discreet:
        return False
    return settings.sound_enabled and cue.key not in settings.muted_sounds


def sound_rows(settings) -> list:
    """One settings row per declared cue, in the order they are declared."""
    return [
        (cue.key, cue.label, cue.key not in settings.muted_sounds)
        for cue in SOUND_CUES
    ]


def toggled_mutes(muted, key: str, audible: bool) -> frozenset:
    """The muted set with one cue switched on or off."""
    if audible:
        return frozenset(muted) - {key}
    return frozenset(muted) | {key}


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"



# How often the pill speaks up while the count runs. The check is the more
# frequent of the two because forgetting to close the pill costs the most:
# the work interval stays held and no break falls due at all.
STANDING_CHECK_SECONDS = 10 * 60
STANDING_MOVE_SECONDS = 30 * 60


def standing_cue(previous: int, current: int) -> Optional[str]:
    """The pulse the pill owes as its clock passes from one reading to the next.

    Working in whole periods rather than exact instants means a tick that
    arrives late — or not at all, across a suspend — still fires the cue it
    stepped over. Where both fall together the move cue wins, since it also
    answers the question the check was going to ask.
    """
    if current <= previous:
        return None
    if current // STANDING_MOVE_SECONDS > previous // STANDING_MOVE_SECONDS:
        return "move"
    if current // STANDING_CHECK_SECONDS > previous // STANDING_CHECK_SECONDS:
        return "check"
    return None


def pill_position(fraction: float, screen_height: int, pill_height: int) -> int:
    """Top of the pill for a stored fraction, kept wholly on screen."""
    travel = max(0, int(screen_height) - int(pill_height))
    return int(round(min(1.0, max(0.0, fraction)) * travel))


def pill_fraction(top: int, screen_height: int, pill_height: int) -> float:
    """Fraction to store for a pill dragged to this top edge."""
    travel = max(0, int(screen_height) - int(pill_height))
    if travel <= 0:
        return 0.0
    return min(1.0, max(0.0, float(top) / travel))


def duration_label(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return ngettext("%d second", "%d seconds", seconds) % seconds
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    parts = []
    if hours:
        parts.append(ngettext("%d hour", "%d hours", hours) % hours)
    if minutes:
        parts.append(ngettext("%d minute", "%d minutes", minutes) % minutes)
    return " ".join(parts)


def short_minutes(seconds: int) -> int:
    """Whole minutes, for the button labels the pixel type has room for."""
    return max(1, int(round(max(0, int(seconds)) / 60)))


def idle_credit_threshold(
    idle_credit_seconds: float, break_seconds: float
) -> float:
    """Idle time that earns a break credit, never shorter than a break."""
    return max(float(idle_credit_seconds), float(break_seconds))


def is_wayland_session(environ: Mapping[str, str]) -> bool:
    backend = environ.get("GDK_BACKEND", "").strip().lower()
    if backend:
        return backend.startswith("wayland")
    return environ.get("XDG_SESSION_TYPE", "").strip().lower() == "wayland"


def countdown_color(seconds_remaining: int, urgent: bool) -> str:
    """The clock is bone while there is time and coral in the last ten seconds."""
    return PALETTE["coral"] if urgent else PALETTE["bone"]


def is_urgent(seconds_remaining: int) -> bool:
    """The last ten seconds, where the clock reddens and shudders."""
    return 0 <= int(seconds_remaining) <= 10


def shudder_period(seconds_remaining: int) -> Optional[int]:
    """Milliseconds per shudder frame, tightening under five seconds."""
    if not is_urgent(seconds_remaining):
        return None
    return 80 if seconds_remaining <= 5 else 120


@dataclass(frozen=True)
class BreakView:
    title: str
    countdown: str
    secondary: str
    prompt: str
    can_snooze: bool
    can_skip: bool
    can_return: bool
    can_miss: bool = False
    can_stand: bool = False
    title_color: str = PALETTE["bone"]


def break_view(phase: Phase, seconds_remaining: int, away_seconds: int) -> BreakView:
    # A work phase means the card is counting down to the break itself. Its
    # actions match the break's, so a break can be put off before it
    # interrupts anything.
    if phase is Phase.WORK:
        return BreakView(
            title=_("Break coming up"),
            countdown=format_duration(seconds_remaining),
            secondary=_("Standing up in %s") % format_duration(seconds_remaining),
            prompt=_("Shoulders down.\nTake a few steps."),
            can_snooze=True,
            can_skip=True,
            can_return=False,
        )
    active = phase is Phase.BREAK
    awaiting = phase is Phase.AWAITING_RETURN
    return BreakView(
        title=_("Nice one") if awaiting else _("Up you get"),
        countdown=format_duration(seconds_remaining),
        secondary=_("Up for %s") % format_duration(away_seconds),
        prompt=(
            _("Back to it when\nyou're ready.")
            if awaiting
            else _("Shoulders down.\nTake a few steps.")
        ),
        can_snooze=active,
        can_skip=active,
        can_return=awaiting,
        can_miss=awaiting,
        # A standing desk answers the break in either state: while it runs
        # and once it is over and waiting to be confirmed.
        can_stand=active or awaiting,
        title_color=PALETTE["mint"] if awaiting else PALETTE["bone"],
    )


def break_hint(view: BreakView) -> str:
    """The key line under the buttons, naming only the keys on offer."""
    if view.can_return:
        keys = [_("ENTER")]
    elif view.can_snooze:
        keys = [_("S SNOOZE"), _("K SKIP")]
    else:
        keys = []
    if view.can_stand:
        keys.append(_("T STANDING"))
    return " · ".join(keys)


@dataclass(frozen=True)
class IndicatorView:
    status: str
    can_start_break: bool
    can_reset_work: bool
    can_pause: bool = False
    can_resume: bool = False


def indicator_view(
    phase: Phase,
    seconds_remaining: int,
    away_seconds: int,
    paused_indefinitely: bool = False,
) -> IndicatorView:
    if phase is Phase.PAUSED:
        status = (
            _("Reminders paused")
            if paused_indefinitely
            else _("Paused for %s") % format_duration(seconds_remaining)
        )
        return IndicatorView(status, False, False, can_resume=True)
    if phase is Phase.BREAK:
        return IndicatorView(_("Break in progress"), False, False)
    if phase is Phase.SNOOZED:
        return IndicatorView(
            _("Break snoozed for %s") % format_duration(seconds_remaining),
            False,
            False,
        )
    if phase is Phase.AWAITING_RETURN:
        return IndicatorView(
            _("Up for %s") % format_duration(away_seconds), False, True
        )
    return IndicatorView(
        _("Next break in %s") % format_duration(seconds_remaining),
        True,
        True,
        can_pause=True,
    )


def indicator_label(
    phase: Phase, seconds_remaining: int, show_countdown: bool
) -> str:
    """Text shown next to the top-bar icon, kept short enough for a panel."""
    if not show_countdown:
        return ""
    if phase is Phase.PAUSED:
        return _("Paused")
    if phase in (Phase.WORK, Phase.SNOOZED):
        return format_duration(seconds_remaining)
    return ""


def standing_action_label(standing: bool) -> str:
    """One row that starts the standing counter, or stops it."""
    return _("I'm sitting down") if standing else _("I'm standing now")


def menu_summary(stats: DailyStats) -> str:
    """The menu's day row: block glyphs, then the counts they stand for."""
    summary = outcome_summary(stats)
    if not summary:
        return _("Nothing recorded yet")
    return f"{menu_blocks(stats)}  {summary}"


def menu_blocks(stats: DailyStats, cap: int = 8) -> str:
    """Today's breaks as filled and hollow blocks, for the menu row.

    The panel menu is drawn by the shell and cannot carry the timeline, so
    the outcomes are spelled with block glyphs instead: filled for a break
    that was kept, hollow for one that was not.
    """
    kept = stats.taken + stats.away
    lost = stats.missed + stats.skipped
    if kept + lost > cap:
        # Keep the row short by scaling the blocks down to the cap.
        shown = max(1, round(cap * kept / (kept + lost)))
        return "\u25ae" * shown + "\u25af" * (cap - shown)
    return "\u25ae" * kept + "\u25af" * lost


STYLE_SHEET = b"""
/* The pixel world: flat fills, hard 4px edges, one bitmap face. */
window.pixel-window,
window.pixel-window * {
    font-family: Silkscreen, "Silkscreen", monospace;
}
window.pixel-window {
    background-color: transparent;
}
.pixel-title {
    color: #f2ece0;
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 1px;
}
.pixel-title-done {
    color: #6fe0a8;
}
.pixel-window-title {
    color: #f2ece0;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 2px;
}
.pixel-secondary {
    color: #9a8fb5;
    font-size: 16px;
    letter-spacing: 1px;
}
.pixel-prompt {
    color: #f2ece0;
    font-size: 16px;
    letter-spacing: 1px;
}
.pixel-hint {
    color: #4a3f66;
    font-size: 16px;
    letter-spacing: 2px;
}
.pixel-dock-title {
    color: #ffb03a;
    font-size: 16px;
    letter-spacing: 1px;
}
.pixel-caption {
    color: #9a8fb5;
    font-size: 16px;
    letter-spacing: 2px;
}
.pixel-verdict {
    font-size: 16px;
    letter-spacing: 1px;
}
.pixel-verdict-mint { color: #6fe0a8; }
.pixel-verdict-amber { color: #ffb03a; }
.pixel-verdict-coral { color: #ff5f5f; }
.pixel-verdict-mist { color: #9a8fb5; }
.pixel-rule {
    background-color: #2e2740;
}
button.pixel-button {
    min-height: 40px;
    padding: 0 8px;
    border: 4px solid #4a3f66;
    border-radius: 0;
    background-image: none;
    background-color: #2e2740;
    color: #f2ece0;
    box-shadow: none;
    text-shadow: none;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1px;
    outline-color: #ffb03a;
    outline-style: solid;
    outline-width: 4px;
    outline-offset: -8px;
}
button.pixel-button:hover {
    background-color: #4a3f66;
}
/* Pressed moves the label one art pixel down without changing the size. */
button.pixel-button:active {
    background-color: #231d33;
    border-top-width: 8px;
    border-bottom-width: 0;
}
button.pixel-button:disabled {
    background-color: #1a1524;
    border-color: #2e2740;
    color: #4a3f66;
}
button.pixel-button-primary {
    background-color: #ffb03a;
    border-color: #ffb03a;
    color: #1a1524;
    outline-color: #f2ece0;
}
button.pixel-button-primary:hover {
    background-color: #ffd08a;
    border-color: #ffd08a;
}
button.pixel-button-primary:active {
    background-color: #e09420;
    border-color: #e09420;
}
button.pixel-button-standing {
    background-color: #1a1524;
    border-color: #5fc8ff;
    color: #5fc8ff;
}
button.pixel-button-standing:hover {
    background-color: #2e2740;
}
button.pixel-button-standing:active {
    background-color: #231d33;
}
/* Leaving is the one destructive action on the page, so it wears coral. */
button.pixel-button-danger {
    background-color: #1a1524;
    border-color: #ff5f5f;
    color: #ff5f5f;
}
button.pixel-button-danger:hover {
    background-color: #ff5f5f;
    color: #1a1524;
}
button.pixel-button-danger:active {
    background-color: #231d33;
    color: #ff5f5f;
}
/* Segmented duration cells in the settings panel. */
button.pixel-segment {
    min-height: 40px;
    padding: 0 4px;
    border: 4px solid #4a3f66;
    border-radius: 0;
    background-image: none;
    background-color: #2e2740;
    color: #9a8fb5;
    box-shadow: none;
    text-shadow: none;
    font-size: 16px;
    font-weight: 400;
    outline-color: #ffb03a;
    outline-style: solid;
    outline-width: 4px;
    outline-offset: -8px;
}
button.pixel-segment:hover {
    background-color: #4a3f66;
    color: #f2ece0;
}
button.pixel-segment-on {
    background-color: #ffb03a;
    border-color: #ffb03a;
    color: #1a1524;
}
button.pixel-segment-on:hover {
    background-color: #ffd08a;
    border-color: #ffd08a;
    color: #1a1524;
}
button.pixel-check {
    padding: 0;
    border: 0;
    border-radius: 0;
    background-image: none;
    background-color: transparent;
    box-shadow: none;
    color: #f2ece0;
    font-size: 16px;
    outline-color: #ffb03a;
    outline-style: solid;
    outline-width: 4px;
    outline-offset: -4px;
}
button.pixel-check:hover {
    color: #ffb03a;
}
tooltip.background,
tooltip {
    background-color: #1a1524;
    border: 4px solid #f2ece0;
    border-radius: 0;
    color: #f2ece0;
}
tooltip label {
    font-family: Silkscreen, monospace;
    font-size: 16px;
    color: #f2ece0;
}
"""


class HeatGrid(Gtk.DrawingArea):
    """Twelve weeks of days: a column per week, a row per weekday.

    Tiles are 8 art pixels square with a 2 art pixel gutter, so the grid
    reads as twelve separate weeks rather than one slab. On opening, the
    columns paint left to right.
    """

    # Sunday opens each column; this date anchors the weekday row labels.
    ROW_ANCHOR = date(2026, 7, 26)
    LABEL_ROWS = (1, 3, 5)

    def __init__(self) -> None:
        super().__init__()
        self._weeks: list[list[Optional[str]]] = []
        self._levels: dict[str, Optional[int]] = {}
        self._tooltips: dict[str, str] = {}
        self._months: dict[int, str] = {}
        self._columns_shown = 0
        self._timer = 0
        self.set_has_tooltip(True)
        self.connect("draw", self._on_draw)
        self.connect("query-tooltip", self._on_tooltip)
        self.connect("unmap", lambda *_args: self._stop())

    def set_history(self, history: Sequence[tuple[str, DailyStats]]) -> None:
        self._weeks = heatmap_weeks([day for day, _stats in history])
        self._levels = {day: heat_level(stats) for day, stats in history}
        self._tooltips = {day: day_tooltip(day, stats) for day, stats in history}
        self._months = {}
        shown = ""
        for column, days in enumerate(self._weeks):
            first = next((day for day in days if day), None)
            if first is None:
                continue
            month = date.fromisoformat(first).strftime("%b").upper()
            if month != shown:
                shown = month
                self._months[column] = month
        width, height = pixels.heat_grid_size(len(self._weeks))
        self.set_size_request(width, height + ap(6))
        self.queue_draw()

    def play_fill(self) -> None:
        """Paint the columns in, left to right, 40 ms apart."""
        self._stop()
        if not ui.animations_enabled():
            self._columns_shown = len(self._weeks)
            self.queue_draw()
            return
        self._columns_shown = 0
        self._timer = GLib.timeout_add(40, self._next_column)
        self.queue_draw()

    def _stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._columns_shown = len(self._weeks)

    def _next_column(self) -> bool:
        self._columns_shown += 1
        self.queue_draw()
        if self._columns_shown >= len(self._weeks):
            self._timer = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_draw(self, _area, context) -> bool:
        tile = ap(pixels.HEAT_TILE)
        step = ap(pixels.HEAT_TILE + pixels.HEAT_GUTTER)
        left_edge = ap(pixels.HEAT_LABELS + pixels.HEAT_GUTTER)
        top = ap(6)
        context.select_font_face("Silkscreen")
        context.set_font_size(16)
        context.set_source_rgb(*pixels.rgb(PALETTE["mist"]))
        for row in self.LABEL_ROWS:
            name = (self.ROW_ANCHOR + timedelta(days=row)).strftime("%a").upper()
            extents = context.text_extents(name)
            context.move_to(
                left_edge - ap(2) - extents.width - extents.x_bearing,
                top + row * step + tile - ART,
            )
            context.show_text(name)
        for column, month in self._months.items():
            if column >= self._columns_shown:
                continue
            context.move_to(left_edge + column * step, top - ART)
            context.show_text(month)
        for column, days in enumerate(self._weeks):
            if column >= self._columns_shown:
                continue
            for row, day in enumerate(days):
                level = self._levels.get(day) if day else None
                context.set_source_rgb(*pixels.rgb(pixels.heat_hex(level)))
                context.rectangle(
                    left_edge + column * step, top + row * step, tile, tile
                )
                context.fill()
        return False

    def _on_tooltip(self, _widget, x, y, _keyboard, tooltip) -> bool:
        at = pixels.heat_tile_at(x, y - ap(6), len(self._weeks))
        if at is None:
            return False
        column, row = at
        day = self._weeks[column][row]
        text = self._tooltips.get(day) if day else None
        if text is None:
            return False
        tooltip.set_text(text)
        return True


class StandingPill(Gtk.Window):
    """The standing HUD: a bobbing face over stacked digits, docked right.

    It is the only surface in the application with a coloured ring at rest,
    which is what makes standing mode read from across the desk. It is
    dragged up and down the right edge and never sideways.
    """

    WIDTH = ap(11)
    DIGIT_SCALE = ART
    BOB_MS = 500
    PULSE_MS = 120
    PULSE_STILL_MS = 1_500
    # Each pulse ends on the resting sky ring, so a blink is the colour it
    # arrives in and the number of times it comes back.
    PULSE_FRAMES = {
        "hour": (PALETTE["bone"], PALETTE["sky"]),
        "check": (PALETTE["amber"], PALETTE["sky"]),
        "move": (
            PALETTE["mint"],
            PALETTE["sky"],
            PALETTE["mint"],
            PALETTE["sky"],
            PALETTE["mint"],
            PALETTE["sky"],
        ),
    }

    def __init__(self, on_stop, on_move) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=_("Standing"))
        self._on_move = on_move
        self._fraction = 0.5
        self._drag_offset: Optional[float] = None
        self._rows: tuple[str, ...] = ("00", "00")
        self._ring = PALETTE["sky"]
        self._bob = 0
        self._bob_timer = 0
        self._flash = 0
        self._pulse_timer = 0
        ui.keep_above(self)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        ui.use_rgba_visual(self)
        self.set_size_request(self.WIDTH, pixels.pill_height(self._rows))
        self.connect("draw", self._on_draw)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("delete-event", lambda *_args: True)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_border_width(ART * 2)

        self.face = ui.Face(scale=ART, sheet="face-bob")
        self.face.set_face("rest", PALETTE["sky"])
        column.pack_start(self.face, False, False, 0)

        self.digit_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.digit_rows.set_margin_top(ap(2))
        column.pack_start(self.digit_rows, False, False, 0)
        self._digit_widgets: list[ui.SpriteDigits] = []
        self._rules: list[Gtk.DrawingArea] = []

        # A coral cross, the one mark on the pill that reads as "stop": it
        # closes the count and starts the next work interval from here.
        stop_button = Gtk.Button()
        stop_button.get_style_context().add_class("pixel-check")
        stop_button.set_relief(Gtk.ReliefStyle.NONE)
        stop_button.set_tooltip_text(_("Sit down — restarts the work timer"))
        stop_glyph = ui.CloseMark(ART)
        stop_glyph.set_color(PALETTE["coral"])
        stop_button.add(stop_glyph)
        stop_button.connect("clicked", on_stop)
        stop_holder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        stop_holder.set_margin_top(ap(2))
        stop_holder.set_halign(Gtk.Align.CENTER)
        stop_holder.pack_start(stop_button, False, False, 0)
        column.pack_start(stop_holder, False, False, 0)

        self.add(column)
        self._build_rows(self._rows)

    def _build_rows(self, rows: Sequence[str]) -> None:
        for child in self.digit_rows.get_children():
            self.digit_rows.remove(child)
        self._digit_widgets = []
        for index, text in enumerate(rows):
            if index:
                rule = Gtk.DrawingArea()
                rule.set_size_request(ap(5), ART)
                rule.set_halign(Gtk.Align.CENTER)
                rule.set_margin_top(ART)
                rule.set_margin_bottom(ART)
                rule.connect("draw", self._draw_rule)
                self.digit_rows.pack_start(rule, False, False, 0)
            digits = ui.SpriteDigits(scale=self.DIGIT_SCALE)
            digits.set_text(text, PALETTE["bone"])
            digits.set_halign(Gtk.Align.CENTER)
            self.digit_rows.pack_start(digits, False, False, 0)
            self._digit_widgets.append(digits)
        self.digit_rows.show_all()

    @staticmethod
    def _draw_rule(area, context) -> bool:
        context.set_source_rgb(*pixels.rgb(PALETTE["edge"]))
        context.rectangle(
            0, 0, area.get_allocated_width(), area.get_allocated_height()
        )
        context.fill()
        return False

    def set_seconds(self, seconds: int) -> None:
        rows = pixels.pill_rows(seconds)
        if len(rows) != len(self._rows):
            grew = len(rows) > len(self._rows)
            self._rows = rows
            self._build_rows(rows)
            self.resize(self.WIDTH, pixels.pill_height(rows))
            self._place()
            if grew:
                self._flash_ring()
        else:
            self._rows = rows
            for widget, text in zip(self._digit_widgets, rows):
                widget.set_text(text, PALETTE["bone"])

    def _flash_ring(self) -> None:
        """A short sky-bone-sky flash rewards passing the hour."""
        self.pulse("hour")

    def pulse(self, kind: str) -> None:
        """Blink the ring, and blink it differently for each thing it says.

        The ring is the pill's whole voice: nothing here opens, waits or has
        to be dismissed. Colour and beat count carry the meaning — one amber
        blink asks whether you are still up, three mint blinks ask for a set
        — so a glance is enough and a missed one costs nothing.
        """
        frames = self.PULSE_FRAMES.get(kind)
        if frames is None:
            return
        self._stop_pulse()
        if not ui.animations_enabled():
            # The cue carries information, not decoration, so reduced motion
            # gets it as a still: the colour is held, then put back.
            self._ring = frames[0]
            self.queue_draw()
            self._pulse_timer = GLib.timeout_add(
                self.PULSE_STILL_MS, self._end_still_pulse
            )
            return
        # The first frame lands now rather than a beat from now, so the ring
        # answers the moment the cue falls due.
        self._flash = 1
        self._ring = frames[0]
        self.queue_draw()

        def step() -> bool:
            self._ring = frames[self._flash]
            self.queue_draw()
            self._flash += 1
            if self._flash < len(frames):
                return GLib.SOURCE_CONTINUE
            self._pulse_timer = 0
            return GLib.SOURCE_REMOVE

        self._pulse_timer = GLib.timeout_add(self.PULSE_MS, step)

    def _end_still_pulse(self) -> bool:
        self._pulse_timer = 0
        self._ring = PALETTE["sky"]
        self.queue_draw()
        return GLib.SOURCE_REMOVE

    def _stop_pulse(self) -> None:
        if self._pulse_timer:
            GLib.source_remove(self._pulse_timer)
            self._pulse_timer = 0
        self._ring = PALETTE["sky"]
        self.queue_draw()

    def _on_draw(self, _widget, context) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        context.set_operator(1)
        context.set_source_rgb(*pixels.rgb(self._ring))
        context.rectangle(0, 0, width, height)
        context.fill()
        context.set_source_rgb(*pixels.rgb(PALETTE["ink"]))
        context.rectangle(ART, ART, width - 2 * ART, height - 2 * ART)
        context.fill()
        context.set_operator(2)
        return False

    def show_at(self, fraction: float) -> None:
        self._fraction = min(1.0, max(0.0, float(fraction)))
        self.show_all()
        self._place()
        self.present()
        self._slide_in()
        self._start_bob()

    def hide(self) -> None:  # noqa: A003 - matches Gtk.Widget.hide
        self._stop_bob()
        self._stop_pulse()
        super().hide()

    def _start_bob(self) -> None:
        self._stop_bob()
        if not ui.animations_enabled():
            return
        self._bob_timer = GLib.timeout_add(self.BOB_MS, self._next_bob)

    def _stop_bob(self) -> None:
        if self._bob_timer:
            GLib.source_remove(self._bob_timer)
            self._bob_timer = 0

    def _next_bob(self) -> bool:
        self._bob = 1 - self._bob
        self.face.set_face(
            "rest" if self._bob == 0 else "blink", PALETTE["sky"]
        )
        return GLib.SOURCE_CONTINUE

    def _monitor_geometry(self):
        display = Gdk.Display.get_default()
        if display is None:
            return None
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        return monitor.get_geometry() if monitor is not None else None

    def _place(self, offset: int = 0) -> None:
        geometry = self._monitor_geometry()
        if geometry is None:
            return
        width, height = self.get_size()
        self.move(
            geometry.x + geometry.width - width - PILL_EDGE_GAP + offset,
            geometry.y + pill_position(self._fraction, geometry.height, height),
        )

    def _slide_in(self) -> None:
        """Four steps of three art pixels in from off-screen right."""
        if not ui.animations_enabled():
            return
        steps = [ap(9), ap(6), ap(3), 0]
        self._place(steps[0])

        def step() -> bool:
            steps.pop(0)
            self._place(steps[0])
            return GLib.SOURCE_CONTINUE if len(steps) > 1 else GLib.SOURCE_REMOVE

        GLib.timeout_add(40, step)

    def _on_press(self, _widget, event) -> bool:
        if event.button != 1:
            return False
        _x, y = self.get_position()
        self._drag_offset = event.y_root - y
        self._ring = PALETTE["bone"]
        self.queue_draw()
        return True

    def _on_motion(self, _widget, event) -> bool:
        if self._drag_offset is None:
            return False
        geometry = self._monitor_geometry()
        if geometry is None:
            return False
        width, height = self.get_size()
        top = int(event.y_root - self._drag_offset) - geometry.y
        top = max(0, min(max(0, geometry.height - height), top))
        self._fraction = pill_fraction(top, geometry.height, height)
        self.move(
            geometry.x + geometry.width - width - PILL_EDGE_GAP,
            geometry.y + top,
        )
        return True

    def _on_release(self, _widget, _event) -> bool:
        if self._drag_offset is None:
            return False
        self._drag_offset = None
        self._ring = PALETTE["sky"]
        self.queue_draw()
        self._on_move(self._fraction)
        return True


class DockCard(Gtk.Window, ui.PixelFrameWindow):
    """The break in the bottom right corner: what is asked, and what to press.

    Discreet mode exists for the minutes somebody else is watching the
    screen, so this carries the count and the three buttons and nothing that
    is merely nice to see. It never dims, never takes focus, and never moves
    itself into the middle of anything.
    """

    # Wide enough for the longest button label, so the card never changes
    # size when the phase changes under it.
    WIDTH = ap(54)
    EDGE_GAP = ap(3)
    SLIDE = (ap(9), ap(6), ap(3), 0)

    def __init__(self, on_snooze, on_skip, on_return, on_miss, on_stand) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=APP_NAME)
        self._phase = Phase.BREAK
        self.break_seconds = 2 * 60
        self.warning_seconds = 0
        self.set_default_size(self.WIDTH, -1)
        self.set_size_request(self.WIDTH, -1)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_keep_above(True)
        self.get_style_context().add_class("pixel-window")
        self.setup_frame()
        self.set_frame_colors(PALETTE["amber"], PALETTE["ink"])
        self.connect("delete-event", lambda *_args: True)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_border_width(ap(2) + ap(2))

        self.title = ui.pixel_label("", "pixel-dock-title", 0.0)
        card.pack_start(self.title, False, False, 0)
        self.secondary = ui.pixel_label("", "pixel-hint", 0.0)
        self.secondary.set_margin_bottom(ap(2))
        card.pack_start(self.secondary, False, False, 0)

        self.clock = ui.SpriteDigits(scale=ART, big=True)
        self.clock.set_halign(Gtk.Align.CENTER)
        self.clock.set_margin_bottom(ap(2))
        card.pack_start(self.clock, False, False, 0)

        self.progress = ui.CellBar()
        self.progress.set_margin_bottom(ap(3))
        card.pack_start(self.progress, False, False, 0)

        # Stacked rather than in a row: at this width three labels side by
        # side would get eleven art pixels each, and the longest does not fit.
        self.stand_button = ui.pixel_button(_("I'M STANDING"), "standing")
        self.stand_button.connect("clicked", on_stand)
        self.return_button = ui.pixel_button(_("I'M BACK"), "primary")
        self.return_button.connect("clicked", on_return)
        self.snooze_button = ui.pixel_button(_("+%d MIN") % 5)
        self.snooze_button.connect("clicked", on_snooze)
        self.skip_button = ui.pixel_button(_("SKIP"))
        self.skip_button.connect("clicked", on_skip)
        self.miss_button = ui.pixel_button(_("I MISSED IT"), "danger")
        self.miss_button.connect("clicked", on_miss)
        for button in (
            self.stand_button,
            self.return_button,
            self.snooze_button,
            self.skip_button,
            self.miss_button,
        ):
            button.set_no_show_all(True)
            button.set_margin_top(ART)
            card.pack_start(button, False, False, 0)

        self.add(card)

    def set_snooze_seconds(self, seconds: int) -> None:
        self.snooze_button.set_label(_("+%d MIN") % max(1, seconds // 60))

    def set_break_seconds(self, seconds: int) -> None:
        self.break_seconds = max(1, int(seconds))

    def set_warning_seconds(self, seconds: int) -> None:
        self.warning_seconds = max(0, int(seconds))

    def update_state(
        self, phase: Phase, seconds_remaining: int, away_seconds: int
    ) -> None:
        view = break_view(phase, seconds_remaining, away_seconds)
        self._phase = phase
        self.title.set_text(view.title)
        self.secondary.set_text(view.secondary)
        urgent = is_urgent(seconds_remaining) and phase is Phase.BREAK
        self.clock.set_text(
            view.countdown, PALETTE["coral"] if urgent else PALETTE["bone"]
        )
        total = self.warning_seconds if phase is Phase.WORK else self.break_seconds
        self.progress.set_accent(PALETTE["amber"])
        self.progress.set_filled(pixels.filled_cells(seconds_remaining, total))
        self.stand_button.set_visible(view.can_stand and not view.can_return)
        self.return_button.set_visible(view.can_return)
        self.snooze_button.set_visible(view.can_snooze)
        self.skip_button.set_visible(view.can_skip)
        self.miss_button.set_visible(view.can_miss)

    def reveal(self, pill_height: int = 0) -> None:
        if self.get_visible():
            return
        self.show_all()
        self._place(pill_height, self.SLIDE[0] if ui.animations_enabled() else 0)
        self.present()
        if ui.animations_enabled():
            self._slide_up(pill_height)

    def _slide_up(self, pill_height: int) -> None:
        steps = list(self.SLIDE[1:])

        def step() -> bool:
            self._place(pill_height, steps.pop(0))
            return GLib.SOURCE_CONTINUE if steps else GLib.SOURCE_REMOVE

        GLib.timeout_add(40, step)

    def _place(self, pill_height: int = 0, drop: int = 0) -> None:
        """The bottom right corner, stepping left of a pill parked in it."""
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() if display else None
        if monitor is None:
            return
        area = monitor.get_workarea()
        width, height = self.get_size()
        # The pill is pinned to the right edge and can be dragged low enough
        # to sit in this corner; where it would, the card steps left of it.
        clearance = StandingPill.WIDTH + PILL_EDGE_GAP + ap(2) if pill_height else 0
        self.move(
            area.x + area.width - width - self.EDGE_GAP - clearance,
            area.y + area.height - height - self.EDGE_GAP + drop,
        )


class DimmerWindow(Gtk.Window):
    """A scanlined cover for the monitors that are not showing the card."""

    BANDS = 6

    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        ui.keep_above(self)
        self.set_accept_focus(False)
        self.set_type_hint(Gdk.WindowTypeHint.SPLASHSCREEN)
        self._bands = self.BANDS
        self.connect("draw", self._on_draw)
        self.connect("delete-event", lambda *_args: True)

    def cover_monitor(self, monitor_index: int) -> None:
        screen = self.get_screen()
        if screen is None:
            return
        self.fullscreen_on_monitor(screen, monitor_index)
        self._wipe_down()

    def _wipe_down(self) -> None:
        if not ui.animations_enabled():
            self._bands = self.BANDS
            self.queue_draw()
            return
        self._bands = 0
        self.queue_draw()

        def step() -> bool:
            self._bands += 1
            self.queue_draw()
            return (
                GLib.SOURCE_CONTINUE if self._bands < self.BANDS else GLib.SOURCE_REMOVE
            )

        GLib.timeout_add(40, step)

    def _on_draw(self, _widget, context) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        band = height / self.BANDS
        covered = height if self._bands >= self.BANDS else int(band * self._bands)
        context.set_source_rgb(*pixels.rgb(PALETTE["void"]))
        context.rectangle(0, 0, width, covered)
        context.fill()
        context.set_source_rgb(*pixels.rgb(PALETTE["ink"]))
        for y in range(0, covered, 2 * ART):
            context.rectangle(0, y, width, ART)
        context.fill()
        return False


class BreakWindow(Gtk.ApplicationWindow, ui.PixelFrameWindow):
    """The card that interrupts you: clock, bar, prompt, actions, day track."""

    WIDTH = ap(120)
    HEIGHT = ap(128)
    TICK_MS = 40

    def __init__(
        self,
        application: Gtk.Application,
        break_seconds: int,
        on_snooze,
        on_skip,
        on_return,
        on_miss,
        on_stand,
        wayland: bool = False,
    ) -> None:
        super().__init__(application=application, title=_("Time to stand up"))
        self.break_seconds = break_seconds
        self.warning_seconds = 0
        self._wayland = wayland
        self._clock = 0
        self._timer = 0
        self._phase: Optional[Phase] = None
        self.set_role("stand-up-break")
        self.set_default_size(self.WIDTH, self.HEIGHT)
        self.set_size_request(self.WIDTH, self.HEIGHT)
        ui.keep_above(self)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_urgency_hint(True)
        self.get_style_context().add_class("pixel-window")
        self.setup_frame()
        self.connect("delete-event", self._ignore_close)
        self.connect("key-press-event", self._on_key_press)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_border_width(ap(2) + ui.CARD_PADDING)

        self.title = ui.pixel_label(_("Time to stand up"), "pixel-title")
        card.pack_start(self.title, False, False, 0)

        self.countdown = ui.Countdown()
        self.countdown.set_margin_top(ap(3))
        card.pack_start(self.countdown, False, False, 0)

        self.secondary = ui.pixel_label("", "pixel-secondary")
        self.secondary.set_margin_top(ap(2))
        card.pack_start(self.secondary, False, False, 0)

        self.progress = ui.CellBar()
        self.progress.set_margin_top(ap(4))
        card.pack_start(self.progress, False, False, 0)

        self.prompt = ui.pixel_label(
            _("Shoulders down.\nTake a few steps."), "pixel-prompt"
        )
        self.prompt.set_justify(Gtk.Justification.CENTER)
        self.prompt.set_margin_top(ap(4))
        card.pack_start(self.prompt, False, False, 0)

        # Row one carries the full-width action; row two the pair beneath it.
        self.first_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self.return_button = ui.pixel_button(_("I'm back"), "primary")
        self.return_button.set_no_show_all(True)
        self.return_button.connect("clicked", on_return)
        self.stand_button = ui.pixel_button(
            _("I'm standing — keep count"), "standing"
        )
        self.stand_button.set_no_show_all(True)
        self.stand_button.connect("clicked", on_stand)
        self.first_row.pack_start(self.return_button, True, True, 0)
        self.first_row.pack_start(self.stand_button, True, True, 0)

        self.burst = ui.Burst()
        first_row_overlay = Gtk.Overlay()
        first_row_overlay.set_margin_top(ap(6))
        first_row_overlay.add(self.first_row)
        first_row_overlay.add_overlay(self.burst)
        first_row_overlay.set_overlay_pass_through(self.burst, True)
        card.pack_start(first_row_overlay, False, False, 0)

        self.second_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(2))
        self.second_row.set_margin_top(ap(2))
        self.snooze_button = ui.pixel_button(_("5 more min"))
        self.snooze_button.set_no_show_all(True)
        self.snooze_button.connect("clicked", on_snooze)
        self.skip_button = ui.pixel_button(_("Skip it"))
        self.skip_button.set_no_show_all(True)
        self.skip_button.connect("clicked", on_skip)
        self.miss_button = ui.pixel_button(_("Didn't take it"))
        self.miss_button.set_no_show_all(True)
        self.miss_button.connect("clicked", on_miss)
        self.stand_small = ui.pixel_button(_("Still standing"), "standing")
        self.stand_small.set_no_show_all(True)
        self.stand_small.connect("clicked", on_stand)
        for button in (
            self.snooze_button,
            self.skip_button,
            self.miss_button,
            self.stand_small,
        ):
            self.second_row.pack_start(button, True, True, 0)
        card.pack_start(self.second_row, False, False, 0)

        self.hint = ui.pixel_label("", "pixel-hint")
        self.hint.set_margin_top(ap(3))
        card.pack_start(self.hint, False, False, 0)

        card.pack_start(Gtk.Box(), True, True, 0)

        self.track = ui.DayTrack()
        self.track.set_no_show_all(True)
        card.pack_start(self.track, False, False, 0)

        self.scores = ui.ScoreLine()
        self.scores.set_margin_top(ap(2))
        card.pack_start(self.scores, False, False, 0)

        self.wipe = ui.WipeOverlay()
        overlay = Gtk.Overlay()
        overlay.add(card)
        overlay.add_overlay(self.wipe)
        overlay.set_overlay_pass_through(self.wipe, True)
        self.add(overlay)

    # -- state ---------------------------------------------------------

    def set_break_seconds(self, break_seconds: int) -> None:
        self.break_seconds = break_seconds

    def set_warning_seconds(self, warning_seconds: int) -> None:
        self.warning_seconds = warning_seconds

    def set_scores(self, text: str, today_percent: Optional[int]) -> None:
        # The face is the verdict on the day: its disc carries the band.
        self.scores.set_line(
            text,
            "rest" if (today_percent or 0) >= 50 else "flat",
            pixels.band_color(today_percent),
        )

    def set_timeline(
        self, points: Sequence[tuple[float, str]], now: Optional[float] = None
    ) -> None:
        self.track.set_points(points, now)
        # A day without recorded outcomes shows no track at all rather than
        # a bare line that reads as a divider.
        self.track.set_visible(bool(points))

    def set_snooze_seconds(self, snooze_seconds: int) -> None:
        self.snooze_button.set_label(
            _("%d more min") % short_minutes(snooze_seconds)
        )

    def set_work_seconds(self, work_seconds: int) -> None:
        self.return_button.set_label(
            _("I'm back — start %d min") % short_minutes(work_seconds)
        )

    @staticmethod
    def _ignore_close(*_args) -> bool:
        return True

    def _on_key_press(self, _window, event) -> bool:
        """Offer keyboard equivalents while keeping Escape inert."""
        if event.keyval == Gdk.KEY_Escape:
            return True
        if self.snooze_button.get_visible() and event.keyval in (
            Gdk.KEY_s,
            Gdk.KEY_S,
        ):
            self.snooze_button.clicked()
            return True
        if self.skip_button.get_visible() and event.keyval in (
            Gdk.KEY_k,
            Gdk.KEY_K,
        ):
            self.skip_button.clicked()
            return True
        if event.keyval in (Gdk.KEY_t, Gdk.KEY_T):
            for button in (self.stand_button, self.stand_small):
                if button.get_visible():
                    button.clicked()
                    return True
        if self.return_button.get_visible() and event.keyval in (
            Gdk.KEY_Return,
            Gdk.KEY_KP_Enter,
            Gdk.KEY_space,
        ):
            self.return_button.clicked()
            return True
        return False

    def update_state(
        self, phase: Phase, seconds_remaining: int, away_seconds: int
    ) -> None:
        view = break_view(phase, seconds_remaining, away_seconds)
        self.set_title(view.title)
        self.title.set_text(view.title)
        context = self.title.get_style_context()
        if view.title_color == PALETTE["mint"]:
            context.add_class("pixel-title-done")
        else:
            context.remove_class("pixel-title-done")
        self.secondary.set_text(view.secondary)
        self.prompt.set_text(view.prompt)
        self._phase = phase
        self._refresh_clock(seconds_remaining)
        total = self.warning_seconds if phase is Phase.WORK else self.break_seconds
        self.progress.set_filled(pixels.filled_cells(seconds_remaining, total))
        self.snooze_button.set_visible(view.can_snooze)
        self.skip_button.set_visible(view.can_skip)
        self.return_button.set_visible(view.can_return)
        self.miss_button.set_visible(view.can_miss)
        self.stand_button.set_visible(view.can_stand and not view.can_return)
        self.stand_small.set_visible(view.can_stand and view.can_return)
        self.hint.set_text(break_hint(view))

    def _refresh_clock(self, seconds_remaining: int) -> None:
        urgent = is_urgent(seconds_remaining) and self._phase is not Phase.AWAITING_RETURN
        blink = True
        shudder = 0
        if ui.animations_enabled():
            # The colon keeps a one-second heartbeat; the digits shudder one
            # art pixel in the last ten seconds.
            blink = (self._clock * self.TICK_MS) % 1000 < 500
            if urgent:
                period = shudder_period(seconds_remaining) or 120
                frames = max(1, period // self.TICK_MS)
                shudder = (self._clock // frames) % 2
        self.countdown.set_time(
            format_duration(seconds_remaining),
            countdown_color(seconds_remaining, urgent),
            blink,
            shudder,
        )

    # -- motion --------------------------------------------------------

    def start_clock(self) -> None:
        if self._timer:
            return
        self._timer = GLib.timeout_add(self.TICK_MS, self._on_tick)

    def stop_clock(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _on_tick(self) -> bool:
        self._clock += 1
        return GLib.SOURCE_CONTINUE

    def play_confirm(self, done) -> None:
        """The mint burst over the button, then the card closes.

        The score-line face is the 8 × 8 art, which has no grin frame, so it
        marks the moment by turning mint rather than by changing expression.
        """
        self.scores.set_line(self.scores._text, "rest", PALETTE["mint"])
        self.burst.play(done)

    def play_missed(self, done) -> None:
        """The one unpleasant motion: a coral ring and a shake."""
        if not ui.animations_enabled():
            self.set_ring(PALETTE["coral"])
            GLib.timeout_add(400, lambda: (done(), GLib.SOURCE_REMOVE)[1])
            return
        frames = [PALETTE["coral"], PALETTE["edge"], PALETTE["coral"], PALETTE["edge"]]
        x, y = self.get_position()

        def step() -> bool:
            self.set_ring(frames.pop(0))
            self.move(x + (ART if len(frames) % 2 else -ART), y)
            if frames:
                return GLib.SOURCE_CONTINUE
            self.move(x, y)
            self.set_ring(PALETTE["edge"])
            done()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(100, step)

    def set_ring(self, color: str) -> None:
        self._ring_color = color
        self.queue_draw()

    def _on_frame_draw(self, _widget, context) -> bool:
        ui.paint_frame(
            context,
            self.get_allocated_width(),
            self.get_allocated_height(),
            ring=getattr(self, "_ring_color", PALETTE["edge"]),
        )
        return False

    def enforce_front(self) -> None:
        self.set_keep_above(True)
        self.deiconify()
        if self._wayland:
            # Wayland ignores keep-above and explicit placement, so the card
            # claims the screen instead of being positioned over it.
            self.fullscreen()
        self.present()
        self.start_clock()

    def reveal(self) -> None:
        """Open with the six-band wipe from the centre out."""
        self.wipe.play()


class StatsWindow(Gtk.Window, ui.PixelFrameWindow):
    """The score screen: the week, the day, and twelve weeks of tiles."""

    WIDTH = ap(152)
    SCORE_SCALE = 3 * ART

    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=_("Score"))
        self.set_default_size(self.WIDTH, ap(210))
        self.set_size_request(self.WIDTH, -1)
        self.set_position(Gtk.WindowPosition.CENTER)
        ui.page_window(self)
        self.get_style_context().add_class("pixel-window")
        self.setup_frame()
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key_press)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_border_width(ap(2) + ap(6))

        card.pack_start(
            ui.page_header(_("SCORE"), lambda *_args: self.hide()), False, False, 0
        )

        caption = ui.pixel_label(_("THIS WEEK"), "pixel-caption", 0.0)
        caption.set_margin_top(ap(6))
        card.pack_start(caption, False, False, 0)

        score_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(2))
        score_row.set_margin_top(ap(2))
        self.score = ui.SpriteDigits(scale=self.SCORE_SCALE, big=True)
        self.score.set_halign(Gtk.Align.START)
        self.percent = ui.PercentMark(self.SCORE_SCALE // 2)
        self.face = ui.Face(scale=6)
        self.face.set_halign(Gtk.Align.END)
        self.face.set_valign(Gtk.Align.CENTER)
        score_row.pack_start(self.score, False, False, 0)
        score_row.pack_start(self.percent, False, False, 0)
        score_row.pack_end(self.face, False, False, 0)
        card.pack_start(score_row, False, False, 0)

        self.verdict = ui.pixel_label("", "pixel-verdict", 0.0)
        self.verdict.set_margin_top(ap(4))
        card.pack_start(self.verdict, False, False, 0)

        self.today_score = ui.pixel_label("", "pixel-secondary", 0.0)
        self.today_score.set_margin_top(ap(2))
        card.pack_start(self.today_score, False, False, 0)

        card.pack_start(self._rule(), False, False, 0)

        today_caption = ui.pixel_label(_("TODAY"), "pixel-caption", 0.0)
        card.pack_start(today_caption, False, False, 0)

        self.track = ui.DayTrack(height_ap=8)
        self.track.set_margin_top(ap(2))
        card.pack_start(self.track, False, False, 0)

        hours = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hours.set_margin_top(ap(2))
        self.track_start = ui.pixel_label("", "pixel-hint", 0.0)
        self.track_start.set_hexpand(True)
        self.track_end = ui.pixel_label("", "pixel-hint", 1.0)
        hours.pack_start(self.track_start, True, True, 0)
        hours.pack_start(self.track_end, False, False, 0)
        card.pack_start(hours, False, False, 0)

        legend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(4))
        legend.set_margin_top(ap(4))
        for outcome, word in (
            ("taken", _("TAKEN")),
            ("away", _("AWAY")),
            ("missed", _("MISSED")),
            ("skipped", _("SKIPPED")),
            ("snoozed", _("SNOOZED")),
        ):
            entry = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ART)
            entry.pack_start(self._swatch(pixels.MARK_COLORS[outcome]), False, False, 0)
            entry.pack_start(ui.pixel_label(word, "pixel-caption"), False, False, 0)
            legend.pack_start(entry, False, False, 0)
        card.pack_start(legend, False, False, 0)

        card.pack_start(self._rule(), False, False, 0)

        weeks_caption = ui.pixel_label(_("TWELVE WEEKS"), "pixel-caption", 0.0)
        card.pack_start(weeks_caption, False, False, 0)

        self.days_grid = HeatGrid()
        self.days_grid.set_margin_top(ap(2))
        card.pack_start(self.days_grid, False, False, 0)

        scale = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ART)
        scale.set_margin_top(ap(2))
        scale.set_margin_start(ap(18))
        scale.pack_start(ui.pixel_label(_("LESS"), "pixel-caption"), False, False, 0)
        for level in range(len(pixels.HEAT_SHADES)):
            scale.pack_start(self._swatch(pixels.heat_hex(level)), False, False, 0)
        scale.pack_start(ui.pixel_label(_("MORE"), "pixel-caption"), False, False, 0)
        card.pack_start(scale, False, False, 0)

        card.pack_start(self._rule(), False, False, 0)

        self.today_line = ui.pixel_label("", "pixel-prompt", 0.0)
        card.pack_start(self.today_line, False, False, 0)
        self.week_line = ui.pixel_label("", "pixel-prompt", 0.0)
        self.week_line.set_margin_top(ap(2))
        card.pack_start(self.week_line, False, False, 0)

        self.add(card)

    @staticmethod
    def _swatch(color: str) -> Gtk.DrawingArea:
        swatch = Gtk.DrawingArea()
        swatch.set_size_request(ap(4), ap(4))
        swatch.set_valign(Gtk.Align.CENTER)

        def draw(area, context) -> bool:
            context.set_source_rgb(*pixels.rgb(color))
            context.rectangle(
                0, 0, area.get_allocated_width(), area.get_allocated_height()
            )
            context.fill()
            return False

        swatch.connect("draw", draw)
        return swatch

    @staticmethod
    def _rule() -> Gtk.DrawingArea:
        rule = Gtk.DrawingArea()
        rule.set_size_request(-1, ART)
        rule.set_margin_top(ap(8))
        rule.set_margin_bottom(ap(8))

        def draw(area, context) -> bool:
            context.set_source_rgb(*pixels.rgb(PALETTE["slate"]))
            context.rectangle(
                0, 0, area.get_allocated_width(), area.get_allocated_height()
            )
            context.fill()
            return False

        rule.connect("draw", draw)
        return rule

    def _on_delete(self, *_args) -> bool:
        self.hide()
        return True

    def _on_key_press(self, _window, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def update_stats(
        self,
        history: Sequence[tuple[str, DailyStats]],
        timeline: tuple[int, int, list[tuple[float, str]]],
        now_minutes: int = 0,
    ) -> None:
        """Refresh from the history's day keys and stats, today last."""
        self._now_minutes = now_minutes
        week = list(history[-WEEK_DAYS:])
        start_minutes, end_minutes, points = timeline
        now = min(1.0, max(0.0, (self._now_minutes - start_minutes) / max(1, end_minutes - start_minutes)))
        self.track.set_points(points, now)
        self.track_start.set_text(
            f"{start_minutes // 60:02d}:{start_minutes % 60:02d}"
        )
        self.track_end.set_text(f"{end_minutes // 60:02d}:{end_minutes % 60:02d}")
        today_stats = week[-1][1] if week else DailyStats()
        week_total = aggregate_stats(stats for _day, stats in week)
        percent = adherence_percent(week_total)
        self._score_target = percent
        self.score.set_text(
            "" if percent is None else str(percent), pixels.band_color(percent)
        )
        self.percent.set_visible(percent is not None)
        self.percent.set_color(pixels.band_color(percent))
        self.face.set_face(
            pixels.face_expression(percent), pixels.band_color(percent)
        )
        self.verdict.set_text(rating_label(percent))
        verdict_context = self.verdict.get_style_context()
        for band in ("mint", "amber", "coral", "mist"):
            verdict_context.remove_class(f"pixel-verdict-{band}")
        verdict_context.add_class(
            "pixel-verdict-%s"
            % {
                PALETTE["mint"]: "mint",
                PALETTE["amber"]: "amber",
                PALETTE["coral"]: "coral",
                PALETTE["mist"]: "mist",
            }[pixels.band_color(percent)]
        )
        self.today_score.set_text(
            _("Today %s") % score_headline(adherence_percent(today_stats))
        )
        self.today_line.set_text(summary_label(today_stats))
        self.week_line.set_text(week_label(week_total))
        self.days_grid.set_history(history)

    def play_open(self) -> None:
        """Count the score up and paint the grid in, column by column."""
        self.days_grid.play_fill()
        target = getattr(self, "_score_target", None)
        if target is not None and target >= 85:
            self.face.play_grin(hold="grin1")
        if target is None or not ui.animations_enabled():
            return
        color = pixels.band_color(target)
        steps = [round(target * step / 20) for step in range(1, 21)]

        def step() -> bool:
            self.score.set_text(str(steps.pop(0)), color)
            return GLib.SOURCE_CONTINUE if steps else GLib.SOURCE_REMOVE

        self.score.set_text("0", color)
        GLib.timeout_add(25, step)


class SettingsPanel(Gtk.Window, ui.PixelFrameWindow):
    """The settings that are set once: durations, counting, away credit."""

    WIDTH = ap(140)

    def __init__(self, settings, on_change) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=_("Settings"))
        self._on_change = on_change
        self._segments: dict[str, list[tuple[Gtk.Button, int]]] = {}
        self._checks: dict[str, tuple[Gtk.Button, Gtk.DrawingArea]] = {}
        self._values: dict[str, bool] = {}
        self.set_default_size(self.WIDTH, -1)
        self.set_size_request(self.WIDTH, -1)
        self.set_position(Gtk.WindowPosition.CENTER)
        ui.page_window(self)
        self.get_style_context().add_class("pixel-window")
        self.setup_frame()
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key_press)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_border_width(ap(2) + ap(6))

        card.pack_start(
            ui.page_header(_("SETTINGS"), lambda *_args: self.hide()), False, False, 0
        )

        card.pack_start(self._group(_("WORK INTERVAL")), False, False, 0)
        card.pack_start(
            self._segmented(
                "work_seconds",
                [(str(seconds // 60), seconds) for seconds in WORK_PRESETS],
                settings.work_seconds,
            ),
            False,
            False,
            0,
        )

        card.pack_start(self._group(_("BREAK LENGTH")), False, False, 0)
        card.pack_start(
            self._segmented(
                "break_seconds",
                [(str(seconds // 60), seconds) for seconds in BREAK_PRESETS],
                settings.break_seconds,
            ),
            False,
            False,
            0,
        )

        card.pack_start(self._group(_("COUNTING")), False, False, 0)
        for key, label, value in (
            (
                "active_only",
                _("Count only while I'm active"),
                settings.mode is TimingMode.ACTIVE,
            ),
            (
                "idle_reset_enabled",
                _("Leaving the desk counts as a break"),
                settings.idle_reset_enabled,
            ),
            (
                "show_countdown",
                _("Show the countdown in the top bar"),
                settings.show_countdown,
            ),
        ):
            card.pack_start(self._checkbox(key, label, value), False, False, 0)

        # The eye break: its own switch, its own interval, and one row per
        # prompt, built from the prompt table so a prompt added later shows up.
        card.pack_start(self._group(_("EYE BREAKS")), False, False, 0)
        card.pack_start(
            self._checkbox(
                "eye_breaks_enabled",
                _("Rest my eyes on a timer"),
                settings.eye_breaks_enabled,
            ),
            False,
            False,
            0,
        )
        self.eye_rows = []
        interval = self._segmented(
            "eye_interval_seconds",
            [
                (_("%d MIN") % (seconds // 60), seconds)
                for seconds in eyes.INTERVAL_PRESETS
            ],
            settings.eye_interval_seconds,
        )
        interval.set_margin_start(ap(6))
        self.eye_rows.append(interval)
        card.pack_start(interval, False, False, 0)
        for prompt in eyes.PROMPTS:
            row = self._checkbox(
                "prompt:" + prompt.key,
                prompt.setting_label,
                prompt.key not in settings.muted_prompts,
            )
            row.set_margin_start(ap(6))
            self.eye_rows.append(row)
            card.pack_start(row, False, False, 0)
        self._apply_eye_master(settings.eye_breaks_enabled)

        # Sound is one master switch over a list built from the cue registry,
        # so a sound added in a later version arrives with its own row here.
        # The list itself folds away: it is set once and grows every release.
        card.pack_start(self._group(_("SOUND")), False, False, 0)
        card.pack_start(
            self._checkbox("sound_enabled", _("Play sounds"), settings.sound_enabled),
            False,
            False,
            0,
        )
        header, body = self._fold(_("WHICH SOUNDS"))
        header.set_margin_start(ap(6))
        card.pack_start(header, False, False, 0)
        self.sound_rows = [header]
        for key, label, audible in sound_rows(settings):
            row = self._checkbox("sound:" + key, label, audible)
            row.set_margin_start(ap(12))
            self.sound_rows.append(row)
            body.pack_start(row, False, False, 0)
        card.pack_start(body, False, False, 0)
        self.apply_sound_master(settings.sound_enabled)

        card.pack_start(self._group(_("AWAY COUNTS AFTER")), False, False, 0)
        card.pack_start(
            self._segmented(
                "idle_credit_seconds",
                [
                    (_("%d MIN") % (seconds // 60), seconds)
                    for seconds in IDLE_CREDIT_PRESETS
                ],
                settings.idle_credit_seconds,
            ),
            False,
            False,
            0,
        )

        done = ui.pixel_button(_("Done"))
        done.set_margin_top(ap(8))
        done.connect("clicked", lambda *_args: self.hide())
        card.pack_start(done, False, False, 0)

        # The list is longer than some screens are tall, so it scrolls rather
        # than running off the bottom with the Done button on it.
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(self._room_on_screen())
        scroller.add(card)
        self.add(scroller)

    @staticmethod
    def _room_on_screen() -> int:
        """How tall the panel may grow before it stops fitting."""
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() if display else None
        if monitor is None:
            return 900
        return max(480, int(monitor.get_workarea().height * 0.9))

    def apply_eye_master(self, enabled: bool) -> None:
        """The interval and the prompt list mean nothing with the timer off."""
        self._apply_eye_master(enabled)

    def _apply_eye_master(self, enabled: bool) -> None:
        for row in self.eye_rows:
            row.set_sensitive(bool(enabled))

    def apply_sound_master(self, enabled: bool) -> None:
        """The per-cue rows mean nothing while the master switch is off."""
        for row in self.sound_rows:
            row.set_sensitive(bool(enabled))

    def _fold(self, title: str, open_at_first: bool = False):
        """A caption that opens and shuts the rows beneath it.

        The sound list is one row per declared cue, so it grows every time a
        sound is added and pushes everything under it off the panel. Folded
        away it costs one line, which is what a list you set once and forget
        should cost.
        """
        header = Gtk.Button()
        header.get_style_context().add_class("pixel-check")
        header.set_relief(Gtk.ReliefStyle.NONE)
        header.set_margin_top(ap(8))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(2))
        mark = ui.FoldMark(open_at_first)
        mark.set_valign(Gtk.Align.CENTER)
        row.pack_start(mark, False, False, 0)
        row.pack_start(ui.pixel_label(title, "pixel-caption", 0.0), False, False, 0)
        header.add(row)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body.set_no_show_all(not open_at_first)
        body.set_visible(open_at_first)

        def toggle(_button) -> None:
            shown = not body.get_visible()
            body.set_no_show_all(not shown)
            body.set_visible(shown)
            if shown:
                body.show_all()
            mark.set_open(shown)

        header.connect("clicked", toggle)
        return header, body

    @staticmethod
    def _group(text: str) -> Gtk.Label:
        label = ui.pixel_label(text, "pixel-caption", 0.0)
        label.set_margin_top(ap(8))
        label.set_margin_bottom(ap(2))
        return label

    def _segmented(self, key: str, choices, active) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(2))
        row.set_homogeneous(True)
        self._segments[key] = []
        for label, value in choices:
            button = Gtk.Button(label=label)
            button.get_style_context().add_class("pixel-segment")
            button.connect("clicked", self._segment_clicked, key, value)
            row.pack_start(button, True, True, 0)
            self._segments[key].append((button, value))
        self._select(key, active)
        return row

    def _select(self, key: str, active) -> None:
        for button, value in self._segments.get(key, []):
            context = button.get_style_context()
            if value == active:
                context.add_class("pixel-segment-on")
            else:
                context.remove_class("pixel-segment-on")

    def _segment_clicked(self, _button, key: str, value: int) -> None:
        self._select(key, value)
        self._on_change(key, value)

    def _checkbox(self, key: str, label: str, value: bool) -> Gtk.Button:
        button = Gtk.Button()
        button.get_style_context().add_class("pixel-check")
        button.set_relief(Gtk.ReliefStyle.NONE)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(2))
        box = Gtk.DrawingArea()
        box.set_size_request(6 * ART, 6 * ART)
        box.set_valign(Gtk.Align.CENTER)
        self._values[key] = bool(value)
        box.connect(
            "draw",
            lambda area, context, key=key: ui.SPRITES.paint(
                context,
                "checkbox-on" if self._values[key] else "checkbox-off",
                0,
                0,
                ART,
                PALETTE["amber"] if self._values[key] else PALETTE["edge"],
            ),
        )
        text = ui.pixel_label(label, "pixel-prompt", 0.0)
        text.set_line_wrap(True)
        # A wrapping label asks for the width of its longest word and no more,
        # so a two-word label breaks in half. A minimum width stops that.
        text.set_width_chars(26)
        row.pack_start(box, False, False, 0)
        row.pack_start(text, False, False, 0)
        button.add(row)
        button.set_margin_top(ap(2))
        button.connect("clicked", self._check_clicked, key)
        self._checks[key] = (button, box)
        return button

    def _check_clicked(self, _button, key: str) -> None:
        self._values[key] = not self._values[key]
        self._checks[key][1].queue_draw()
        self._on_change(key, self._values[key])

    def _on_delete(self, *_args) -> bool:
        self.hide()
        return True

    def _on_key_press(self, _window, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False


class ControlWindow(Gtk.Window, ui.PixelFrameWindow):
    """The application's own hub, in the pixel language the menu cannot use.

    GNOME Shell draws the top-bar menu from a list of labels sent over DBus,
    so the application never paints those rows and cannot give them the
    interface face. Everything that used to live in that menu lives here
    instead, leaving the menu the status it can only ever be.
    """

    WIDTH = ap(120)

    def __init__(
        self,
        on_start_break,
        on_return,
        on_standing,
        on_pause,
        on_resume,
        on_score,
        on_settings,
        on_quit,
    ) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=APP_NAME)
        self.set_default_size(self.WIDTH, -1)
        self.set_size_request(self.WIDTH, -1)
        self.set_position(Gtk.WindowPosition.CENTER)
        ui.page_window(self)
        self.get_style_context().add_class("pixel-window")
        self.setup_frame()
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key_press)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.set_border_width(ap(2) + ap(6))

        card.pack_start(
            ui.page_header(_("STAND UP"), lambda *_args: self.hide()), False, False, 0
        )

        self.status = ui.pixel_label("", "pixel-secondary", 0.0)
        self.status.set_margin_top(ap(4))
        card.pack_start(self.status, False, False, 0)

        self.summary = ui.pixel_label("", "pixel-hint", 0.0)
        self.summary.set_margin_top(ap(2))
        card.pack_start(self.summary, False, False, 0)

        self.start_button = ui.pixel_button(_("Start a break now"))
        self.start_button.set_margin_top(ap(8))
        self.start_button.connect("clicked", on_start_break)
        card.pack_start(self.start_button, False, False, 0)

        self.return_button = ui.pixel_button(_("I'm back — restart the timer"))
        self.return_button.set_margin_top(ap(2))
        self.return_button.connect("clicked", on_return)
        card.pack_start(self.return_button, False, False, 0)

        self.standing_button = ui.pixel_button(
            standing_action_label(False), "standing"
        )
        self.standing_button.set_margin_top(ap(2))
        self.standing_button.connect("clicked", on_standing)
        card.pack_start(self.standing_button, False, False, 0)

        pause_caption = ui.pixel_label(_("PAUSE REMINDERS"), "pixel-caption", 0.0)
        pause_caption.set_margin_top(ap(8))
        pause_caption.set_margin_bottom(ap(2))
        card.pack_start(pause_caption, False, False, 0)

        self.pause_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(2))
        self.pause_row.set_homogeneous(True)
        self.pause_buttons = []
        for label, seconds in (
            (_("%d MIN") % (PAUSE_PRESETS[0] // 60), PAUSE_PRESETS[0]),
            (_("%d HOUR") % (PAUSE_PRESETS[1] // 3600), PAUSE_PRESETS[1]),
            (_("UNTIL I RESUME"), None),
        ):
            button = Gtk.Button(label=label)
            button.get_style_context().add_class("pixel-segment")
            button.connect("clicked", lambda _b, s=seconds: on_pause(s))
            self.pause_row.pack_start(button, True, True, 0)
            self.pause_buttons.append(button)
        card.pack_start(self.pause_row, False, False, 0)

        self.resume_button = ui.pixel_button(_("Resume reminders"), "primary")
        self.resume_button.set_no_show_all(True)
        self.resume_button.set_margin_top(ap(2))
        self.resume_button.connect("clicked", on_resume)
        card.pack_start(self.resume_button, False, False, 0)

        pages = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=ap(2))
        pages.set_margin_top(ap(8))
        pages.set_homogeneous(True)
        score_button = ui.pixel_button(_("Score"))
        score_button.connect("clicked", on_score)
        settings_button = ui.pixel_button(_("Settings"))
        settings_button.connect("clicked", on_settings)
        pages.pack_start(score_button, True, True, 0)
        pages.pack_start(settings_button, True, True, 0)
        card.pack_start(pages, False, False, 0)

        quit_button = ui.pixel_button(_("Quit"), "danger")
        quit_button.set_margin_top(ap(8))
        quit_button.connect("clicked", on_quit)
        card.pack_start(quit_button, False, False, 0)

        self.add(card)

    def update_state(
        self, view: IndicatorView, summary: str, standing: bool
    ) -> None:
        self.status.set_text(view.status)
        self.summary.set_text(summary)
        self.start_button.set_sensitive(view.can_start_break)
        self.return_button.set_sensitive(view.can_reset_work)
        self.standing_button.set_label(standing_action_label(standing))
        for button in self.pause_buttons:
            button.set_sensitive(view.can_pause)
        self.pause_row.set_visible(not view.can_resume)
        self.resume_button.set_visible(view.can_resume)

    def _on_delete(self, *_args) -> bool:
        self.hide()
        return True

    def _on_key_press(self, _window, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False


class ReminderApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.scheduler: Optional[Scheduler] = None
        self.window: Optional[BreakWindow] = None
        self.stats_window: Optional[StatsWindow] = None
        self.pill: Optional[StandingPill] = None
        self.settings_panel: Optional[SettingsPanel] = None
        self.control_window: Optional[ControlWindow] = None
        self.settings = Settings()
        self.indicator = None
        self.stats = None
        self.status_item = None
        self.stats_item = None
        self.active_item = None
        self.wall_item = None
        self.work_items: dict = {}
        self.break_items: dict = {}
        self.idle_credit_items: dict = {}
        self.countdown_item = None
        self.sound_item = None
        self.idle_item = None
        self._dimmers: list = []
        self._settings_store: Optional[SettingsStore] = None
        self._session_bus = None
        self._lock_subscription = 0
        self._sound = None
        self._player = ""
        self._stats_day = ""
        self._stats_summary = ""
        self._score_day = ""
        self._indicator_label = None
        self._indicator_icon = ICON_NAME
        self._idle_credit_pending = False
        self._standing_since: Optional[float] = None
        self._standing_seconds = 0
        # Discreet is deliberately not saved: it is switched on for a
        # meeting, and being silently muted for a week is the worse bug.
        self.discreet = False
        self.dock: Optional[DockCard] = None
        self.eye_card: Optional[EyeWindow] = None
        self._eye_seconds = 0
        self._eye_index = 0
        self._clock = time.monotonic
        self._suppress_menu_events = False
        self._wayland = False
        self._started = False
        self.startup_failed = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        css = Gtk.CssProvider()
        css.load_from_data(STYLE_SHEET)
        screen = Gdk.Screen.get_default()
        if screen is None:
            raise RuntimeError("no graphical display is available")
        Gtk.StyleContext.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self) -> None:
        if self._started:
            if self.scheduler and self.scheduler.snapshot().phase in (
                Phase.BREAK,
                Phase.AWAITING_RETURN,
            ):
                self._show_break()
            return

        try:
            self._initialize()
        except Exception as error:
            self.startup_failed = True
            print(f"stand-up-reminder: startup failed: {error}", file=sys.stderr)
            GLib.idle_add(self.quit)

    def do_shutdown(self) -> None:
        if self._session_bus and self._lock_subscription:
            self._session_bus.signal_unsubscribe(self._lock_subscription)
            self._lock_subscription = 0
        Gtk.Application.do_shutdown(self)

    def _initialize(self) -> None:
        self._started = True
        config_home = Path(
            os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        )
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        )
        self._settings_store = SettingsStore(
            config_home / "stand-up-reminder" / "settings.json"
        )
        self.stats = StatsStore(data_home / "stand-up-reminder" / "stats.json")
        self.settings = self._settings_store.load()
        self._wayland = is_wayland_session(os.environ)

        work_seconds = self._duration_override(
            "STAND_UP_REMINDER_WORK_SECONDS", self.settings.work_seconds
        )
        break_seconds = self._duration_override(
            "STAND_UP_REMINDER_BREAK_SECONDS", self.settings.break_seconds
        )
        snooze_seconds = self._duration_override(
            "STAND_UP_REMINDER_SNOOZE_SECONDS", self.settings.snooze_seconds
        )
        if work_seconds <= 0 or break_seconds <= 0 or snooze_seconds <= 0:
            raise ValueError("timer durations must be positive")

        self.scheduler = Scheduler(
            work_seconds=work_seconds,
            break_seconds=break_seconds,
            snooze_seconds=snooze_seconds,
            # Overridden durations bypass the settings file's own clamping, so
            # the warning is re-checked against the interval actually in use.
            warning_seconds=min(self.settings.warning_seconds, work_seconds - 1),
            mode=self.settings.mode,
        )
        self.window = BreakWindow(
            self,
            int(break_seconds),
            self._snooze_break,
            self._skip_break,
            self._confirm_return,
            self._missed_break,
            self._stand_up,
            wayland=self._wayland,
        )
        self.window.set_snooze_seconds(int(snooze_seconds))
        self.window.set_work_seconds(int(work_seconds))
        self.window.set_warning_seconds(int(self.scheduler.warning_seconds))
        self._refresh_score_line()
        self._build_indicator()
        self._initialize_sound()
        self._connect_lock_monitor()
        GLib.timeout_add(250, self._tick)
        GLib.timeout_add_seconds(IDLE_POLL_SECONDS, self._poll_idle)
        self._update_interface()

    @staticmethod
    def _duration_override(variable: str, configured: int) -> float:
        raw = os.environ.get(variable)
        return float(configured if raw is None else float(raw))

    def _initialize_sound(self) -> None:
        self._player = ""
        if GSound is None:
            self._player = sound_player()
            return
        try:
            context = GSound.Context()
            context.init()
            self._sound = context
        except GLib.Error as error:  # pragma: no cover - depends on host audio
            print(
                f"stand-up-reminder: sound cues unavailable: {error}",
                file=sys.stderr,
            )

    def _build_indicator(self) -> None:
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            APP_ID,
            ICON_NAME,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_NAME)
        self.indicator.set_icon_full(ICON_NAME, APP_NAME)

        # GNOME Shell draws this menu itself, from labels sent over DBus, so
        # it carries the day's state and nothing else: every action lives in
        # the control window, where the application does its own drawing.
        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label=_("Next break in 30:00"))
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        self.stats_item = Gtk.MenuItem(label=_("Nothing recorded yet"))
        self.stats_item.set_sensitive(False)
        menu.append(self.stats_item)
        menu.append(Gtk.SeparatorMenuItem())

        # The one action that belongs in the menu rather than the control
        # window: it is reached while somebody is already looking at the
        # screen, so opening a window on the way would defeat it.
        self.discreet_item = Gtk.CheckMenuItem(label=_("Discreet mode"))
        self.discreet_item.set_active(False)
        self.discreet_item.connect("toggled", self._toggle_discreet)
        menu.append(self.discreet_item)
        menu.append(Gtk.SeparatorMenuItem())

        open_item = Gtk.MenuItem(label=_("Open Stand Up Reminder"))
        open_item.connect("activate", self._open_control_window)
        menu.append(open_item)
        menu.show_all()
        self.indicator.set_menu(menu)

    def _toggle_discreet(self, item) -> None:
        """Move the reminders out of the way without changing any setting."""
        self.discreet = bool(item.get_active())
        if self.discreet:
            if self.eye_card is not None:
                self.eye_card.finish()
            self._hide_dimmers()
        # A break already on screen moves to the other surface rather than
        # waiting for the next one.
        snapshot = self.scheduler.snapshot()
        if snapshot.phase in (Phase.BREAK, Phase.AWAITING_RETURN):
            self._close_break_surfaces()
            self._show_break()
        self._update_interface()

    def _close_break_surfaces(self) -> None:
        if self.window is not None:
            self.window.hide()
            self.window.stop_clock()
        if self.dock is not None:
            self.dock.hide()
        self._hide_dimmers()

    def _open_control_window(self, _item) -> None:
        if self.control_window is None:
            self.control_window = ControlWindow(
                self._start_break_now,
                self._reset_work_interval,
                self._toggle_standing,
                self._pause_from_control,
                self._resume_reminders,
                self._open_stats_window,
                self._open_settings_panel,
                self._quit_cleanly,
            )
        self._update_interface()
        ui.raise_page(self.control_window)

    def _pause_from_control(self, seconds: Optional[int]) -> None:
        self._pause_reminders(None, seconds)

    def _open_settings_panel(self, _item) -> None:
        if self.settings_panel is None:
            self.settings_panel = SettingsPanel(self.settings, self._panel_changed)
        ui.raise_page(self.settings_panel)

    def _panel_changed(self, key: str, value) -> None:
        """Apply one setting from the panel, saving as it changes."""
        if key == "work_seconds":
            self.scheduler.set_durations(work_seconds=value)
            self.window.set_work_seconds(value)
            self._save_settings(work_seconds=value)
        elif key == "break_seconds":
            self.scheduler.set_durations(break_seconds=value)
            self.window.set_break_seconds(value)
            self._save_settings(break_seconds=value)
        elif key == "idle_credit_seconds":
            self._save_settings(idle_credit_seconds=value)
        elif key == "active_only":
            mode = TimingMode.ACTIVE if value else TimingMode.WALL
            self._apply_transition(self.scheduler.set_mode(mode))
            self._save_settings(mode=mode)
        elif key == "idle_reset_enabled":
            self._save_settings(idle_reset_enabled=value)
        elif key == "sound_enabled":
            self._save_settings(sound_enabled=value)
            if self.settings_panel is not None:
                self.settings_panel.apply_sound_master(value)
        elif key == "eye_breaks_enabled":
            self._save_settings(eye_breaks_enabled=value)
            self._eye_seconds = 0
            if self.settings_panel is not None:
                self.settings_panel.apply_eye_master(value)
        elif key == "eye_interval_seconds":
            self._save_settings(eye_interval_seconds=value)
            self._eye_seconds = 0
        elif key.startswith("prompt:"):
            self._save_settings(
                muted_prompts=toggled_mutes(
                    self.settings.muted_prompts, key[len("prompt:"):], value
                )
            )
        elif key.startswith("sound:"):
            self._save_settings(
                muted_sounds=toggled_mutes(
                    self.settings.muted_sounds, key[len("sound:"):], value
                )
            )
        elif key == "show_countdown":
            self._save_settings(show_countdown=value)
        self._update_interface()

    def _connect_lock_monitor(self) -> None:
        self._session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._lock_subscription = self._session_bus.signal_subscribe(
            "org.gnome.ScreenSaver",
            "org.gnome.ScreenSaver",
            "ActiveChanged",
            "/org/gnome/ScreenSaver",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_lock_signal,
        )
        reply = self._session_bus.call_sync(
            "org.gnome.ScreenSaver",
            "/org/gnome/ScreenSaver",
            "org.gnome.ScreenSaver",
            "GetActive",
            None,
            GLib.VariantType.new("(b)"),
            Gio.DBusCallFlags.NONE,
            2_000,
            None,
        )
        self._set_locked(reply.unpack()[0])

    def _on_lock_signal(
        self, _bus, _sender, _path, _interface, _signal, parameters
    ) -> None:
        self._set_locked(parameters.unpack()[0])

    def _set_locked(self, locked: bool) -> None:
        transition = self.scheduler.set_locked(locked)
        if locked and self.window:
            self.window.hide()
            self._hide_dimmers()
        self._apply_transition(transition)
        if (
            not locked
            and transition is not Transition.START_BREAK
            and self.scheduler.snapshot().phase
            in (Phase.BREAK, Phase.AWAITING_RETURN)
        ):
            self._show_break()
        self._update_interface()

    def _idle_seconds(self) -> Optional[float]:
        if self._session_bus is None:
            return None
        try:
            reply = self._session_bus.call_sync(
                "org.gnome.Mutter.IdleMonitor",
                "/org/gnome/Mutter/IdleMonitor/Core",
                "org.gnome.Mutter.IdleMonitor",
                "GetIdletime",
                None,
                GLib.VariantType.new("(t)"),
                Gio.DBusCallFlags.NONE,
                2_000,
                None,
            )
        except GLib.Error:
            return None
        return reply.unpack()[0] / 1000.0

    def _poll_idle(self) -> bool:
        """Credit a long stretch away from the keyboard as a break taken."""
        if not self.settings.idle_reset_enabled:
            self._idle_credit_pending = False
            return GLib.SOURCE_CONTINUE
        idle_seconds = self._idle_seconds()
        if idle_seconds is None:
            return GLib.SOURCE_CONTINUE
        threshold = idle_credit_threshold(
            self.settings.idle_credit_seconds, self.scheduler.break_seconds
        )
        if idle_seconds >= threshold:
            self._idle_credit_pending = True
        elif self._idle_credit_pending:
            self._idle_credit_pending = False
            if self.scheduler.credit_idle_break(threshold):
                self._record_outcome(BreakOutcome.AWAY)
                self._update_interface()
        return GLib.SOURCE_CONTINUE

    def _tick(self) -> bool:
        transition = self.scheduler.advance()
        self._apply_transition(transition)
        self._advance_eye_clock()
        self._update_interface()
        return GLib.SOURCE_CONTINUE

    def _apply_transition(self, transition: Optional[Transition]) -> None:
        if transition is Transition.WARN_BREAK:
            self._show_warning()
        elif transition is Transition.START_BREAK:
            self._play_sound(SOUND_CUES[0])
            self._show_break()
        elif transition is Transition.BREAK_COMPLETE:
            self._play_sound(SOUND_CUES[1])
        elif transition is Transition.END_BREAK:
            self._close_break_surfaces()

    def _show_warning(self) -> None:
        """Open the break window early, counting down to the break itself."""
        snapshot = self.scheduler.snapshot()
        if snapshot.locked or snapshot.phase is not Phase.WORK:
            return
        # Bring the day track up to the present before it becomes visible.
        self._refresh_score_line()
        self.window.update_state(
            snapshot.phase,
            snapshot.seconds_remaining,
            snapshot.away_seconds,
        )
        self.window.show_all()
        self.window.enforce_front()
        self.window.reveal()

    def _play_sound(self, cue: SoundCue) -> None:
        """The one way the application makes a sound.

        Every cue passes both switches here — the master and its own — so a
        sound added later is silenced by the master without the author of it
        having to remember anything.
        """
        if not sound_allowed(self.settings, cue, self.discreet):
            return
        if self._sound is None:
            # No GSound: our own files still play through whatever the system
            # has. GLib reaps the child, so nothing is left behind.
            if cue.filename and self._player:
                GLib.spawn_async(
                    [self._player, str(sound_dir() / cue.filename)],
                    flags=GLib.SpawnFlags.SEARCH_PATH,
                )
            return
        if cue.filename:
            attributes = {
                GSound.ATTR_MEDIA_FILENAME: str(sound_dir() / cue.filename)
            }
        else:
            attributes = {GSound.ATTR_EVENT_ID: cue.event_id}
        try:
            self._sound.play_simple(attributes, None)
        except GLib.Error:  # pragma: no cover - depends on host audio
            pass

    def _show_break(self) -> None:
        snapshot = self.scheduler.snapshot()
        if snapshot.locked:
            return
        if self.discreet:
            self._show_dock(snapshot)
            return
        self._refresh_score_line()
        self.window.update_state(
            snapshot.phase,
            snapshot.seconds_remaining,
            snapshot.away_seconds,
        )
        self.window.show_all()
        self.window.enforce_front()
        self.window.reveal()
        # The break window has to be realized before GDK can report which
        # monitor it landed on.
        self._show_dimmers()

    def _show_dock(self, snapshot) -> None:
        """The break, docked in the corner: no dimmer, no focus, no fanfare."""
        if self.dock is None:
            self.dock = DockCard(
                self._snooze_break,
                self._skip_break,
                self._confirm_return,
                self._missed_break,
                self._stand_up,
            )
        self.dock.set_snooze_seconds(int(self.scheduler.snooze_seconds))
        self.dock.set_break_seconds(int(self.scheduler.break_seconds))
        self.dock.set_warning_seconds(int(self.scheduler.warning_seconds))
        self.dock.update_state(
            snapshot.phase, snapshot.seconds_remaining, snapshot.away_seconds
        )
        self.dock.reveal(self._pill_bottom())

    def _pill_bottom(self) -> int:
        """How far up the corner is already taken by the standing pill."""
        if self.pill is None or not self.pill.get_visible():
            return 0
        return self.pill.get_size()[0]

    def _show_dimmers(self) -> None:
        """Cover the monitors that do not hold the break card."""
        display = Gdk.Display.get_default()
        gdk_window = self.window.get_window() if self.window else None
        if display is None or gdk_window is None:
            return
        try:
            monitor_count = display.get_n_monitors()
            if monitor_count < 2:
                return
            active_index = self._monitor_index(display, gdk_window, monitor_count)
            while len(self._dimmers) < monitor_count:
                self._dimmers.append(DimmerWindow())
            for index, dimmer in enumerate(self._dimmers):
                if index >= monitor_count or index == active_index:
                    dimmer.hide()
                    continue
                dimmer.show_all()
                dimmer.cover_monitor(index)
        except Exception as error:  # pragma: no cover - display layouts vary
            print(
                f"stand-up-reminder: could not dim other monitors: {error}",
                file=sys.stderr,
            )

    @staticmethod
    def _monitor_index(display, gdk_window, monitor_count: int) -> int:
        """Index of the monitor holding the break window, by geometry."""
        active = display.get_monitor_at_window(gdk_window)
        if active is None:
            return 0
        geometry = active.get_geometry()
        for index in range(monitor_count):
            candidate = display.get_monitor(index).get_geometry()
            if (candidate.x, candidate.y) == (geometry.x, geometry.y):
                return index
        return 0

    def _hide_dimmers(self) -> None:
        for dimmer in self._dimmers:
            dimmer.hide()

    def _update_interface(self) -> None:
        snapshot = self.scheduler.snapshot()
        view = indicator_view(
            snapshot.phase,
            snapshot.seconds_remaining,
            snapshot.away_seconds,
            snapshot.paused_indefinitely,
        )
        self.status_item.set_label(view.status)
        today = today_key()
        summary = self._stats_label(today)
        self.stats_item.set_label(summary)
        if self.control_window is not None:
            self.control_window.update_state(
                view, summary, self._standing_since is not None
            )
        if self._score_day != today:
            self._refresh_score_line()

        icon = PAUSED_ICON_NAME if snapshot.phase is Phase.PAUSED else ICON_NAME
        if icon != self._indicator_icon:
            self._indicator_icon = icon
            self.indicator.set_icon_full(icon, APP_NAME)

        label = indicator_label(
            snapshot.phase,
            snapshot.seconds_remaining,
            self.settings.show_countdown,
        )
        if label != self._indicator_label:
            self._indicator_label = label
            self.indicator.set_label(label, "00:00")

        if (
            snapshot.phase in (Phase.BREAK, Phase.AWAITING_RETURN)
            and not snapshot.locked
        ):
            self.window.update_state(
                snapshot.phase,
                snapshot.seconds_remaining,
                snapshot.away_seconds,
            )
            self.window.set_keep_above(True)
        elif self.window and self.window.get_visible():
            # The window is open as the pre-break countdown; keep it current
            # and close it if a pause, reset, or lock ended the warning.
            in_warning = (
                snapshot.phase is Phase.WORK
                and self.scheduler.warning_seconds > 0
                and snapshot.seconds_remaining <= self.scheduler.warning_seconds
            )
            if in_warning and not snapshot.locked:
                self.window.update_state(
                    snapshot.phase,
                    snapshot.seconds_remaining,
                    snapshot.away_seconds,
                )
            else:
                self.window.hide()
                self.window.stop_clock()
                self._hide_dimmers()

        self._refresh_dock()
        self._refresh_standing_pill()

    def _record_outcome(self, outcome: BreakOutcome) -> None:
        if self.stats is None:
            return
        self.stats.record(outcome)
        self._stats_day = today_key()
        self._stats_summary = menu_summary(self.stats.load(self._stats_day))
        self._refresh_score_line()
        if self.stats_window and self.stats_window.get_visible():
            self._refresh_stats_window()

    @staticmethod
    def _now_minutes() -> int:
        now = datetime.now()
        return now.hour * 60 + now.minute

    def _today_timeline(self, day: str) -> tuple[int, int, list]:
        return timeline_layout(self.stats.load_events(day), self._now_minutes())

    def _now_fraction(self, start_minutes: int, end_minutes: int) -> float:
        """Where the present moment sits on the day track."""
        span = max(1, end_minutes - start_minutes)
        return min(1.0, max(0.0, (self._now_minutes() - start_minutes) / span))

    def _refresh_score_line(self) -> None:
        """Recompute the day and week adherence shown on the break window."""
        if self.stats is None or self.window is None:
            return
        days = last_days(WEEK_DAYS)
        stats_list = self.stats.load_days(days)
        self._score_day = days[-1]
        today_percent = adherence_percent(stats_list[-1])
        self.window.set_scores(
            score_line(
                today_percent, adherence_percent(aggregate_stats(stats_list))
            ),
            today_percent,
        )
        start, end, points = self._today_timeline(days[-1])
        self.window.set_timeline(points, self._now_fraction(start, end))

    def _open_stats_window(self, _item) -> None:
        if self.stats_window is None:
            self.stats_window = StatsWindow()
        self._refresh_stats_window()
        ui.raise_page(self.stats_window)
        self.stats_window.play_open()

    def _refresh_stats_window(self) -> None:
        if self.stats_window is None or self.stats is None:
            return
        days = last_days(GRID_DAYS)
        self.stats_window.update_stats(
            list(zip(days, self.stats.load_days(days))),
            self._today_timeline(days[-1]),
            self._now_minutes(),
        )

    def _stats_label(self, day: str) -> str:
        """Cached daily summary, re-read only when the counters can differ.

        The interface refreshes four times a second, so the stored counters are
        loaded when an outcome is recorded and when the date rolls over rather
        than on every refresh.
        """
        if day != self._stats_day:
            self._stats_day = day
            self._stats_summary = menu_summary(self.stats.load(day))
        return self._stats_summary

    def _save_settings(self, **changes) -> None:
        self.settings = replace(self.settings, **changes)
        try:
            self._settings_store.save(self.settings)
        except OSError as error:
            print(
                f"stand-up-reminder: could not save settings: {error}",
                file=sys.stderr,
            )

    def _start_break_now(self, _item) -> None:
        self._apply_transition(self.scheduler.start_break())
        self._update_interface()

    def _confirm_return(self, _button) -> None:
        transition = self.scheduler.confirm_return()
        if transition is Transition.END_BREAK:
            self._record_outcome(BreakOutcome.TAKEN)
            self._play_sound(EYE_CUES["break_kept"])
            if self.discreet:
                self._close_card(transition)
                return
            # The burst plays over the button and the new mark writes onto
            # the day track before the card goes.
            self.window.play_confirm(lambda: self._close_card(transition))
            self._update_interface()
            return
        self._apply_transition(transition)
        self._update_interface()

    def _missed_break(self, _button) -> None:
        transition = self.scheduler.confirm_return()
        if transition is Transition.END_BREAK:
            self._record_outcome(BreakOutcome.MISSED)
            if self.discreet:
                self._close_card(transition)
                return
            self.window.play_missed(lambda: self._close_card(transition))
            self._update_interface()
            return
        self._apply_transition(transition)
        self._update_interface()

    def _close_card(self, transition: Transition) -> None:
        self._apply_transition(transition)
        self._update_interface()

    def _snooze_break(self, _button) -> None:
        if self.scheduler.snooze_break():
            self._record_outcome(BreakOutcome.SNOOZED)
            self._close_break_surfaces()
        self._update_interface()

    def _skip_break(self, _button) -> None:
        if self.scheduler.skip_break():
            self._record_outcome(BreakOutcome.SKIPPED)
            self._close_break_surfaces()
        self._update_interface()

    def _stand_up(self, _button) -> None:
        """Take the break standing: count it, then start the standing pill."""
        # The break has been counting up since it opened, and standing is a
        # way of taking it rather than a new event, so the pill carries that
        # clock on instead of restarting at zero.
        already_up = self.scheduler.snapshot().away_seconds
        transition = self.scheduler.stand_up()
        if transition is Transition.END_BREAK:
            self._record_outcome(BreakOutcome.TAKEN)
            self._apply_transition(transition)
            self._start_standing(already_up)
        self._update_interface()

    def _start_standing(self, already_up: float = 0.0) -> None:
        """Open the pill, keeping any count that is already running.

        Standing can begin at a break or straight from the menu, and a break
        answered by someone who is already up keeps their clock rather than
        starting a fresh one — that is what "keep count" means.
        """
        if self.pill is None:
            self.pill = StandingPill(self._sit_down, self._standing_pill_moved)
        if self._standing_since is None:
            self._standing_since = self._clock() - max(0.0, float(already_up))
            self._standing_seconds = int(self._clock() - self._standing_since)
        # Time on your feet is the break, so the work interval waits.
        self.scheduler.set_standing(True)
        self.pill.set_seconds(int(self._clock() - self._standing_since))
        self.pill.show_at(self.settings.standing_pill_position)

    def _toggle_standing(self, _item) -> None:
        """Start or stop the standing counter without a break being due."""
        if self._standing_since is None:
            self._start_standing()
        else:
            self._stop_standing()
        self._update_interface()

    def _sit_down(self, _button) -> None:
        self._stop_standing()
        self._update_interface()

    def _stop_standing(self) -> None:
        """Sit back down: close the pill and start the interval afresh.

        What the research counts is uninterrupted sitting, so the clock runs
        from the moment the user sits rather than from the moment they stood
        — a long stand is neither punished with a short interval nor cashed
        in for a longer one.
        """
        if self.pill is not None:
            self.pill.hide()
        if self._standing_since is not None:
            # Sitting down after a stand is the same event as saying you are
            # back from a break, so it earns the same fanfare.
            self._play_sound(EYE_CUES["break_kept"])
        self._standing_since = None
        self._standing_seconds = 0
        self.scheduler.set_standing(False)
        self.scheduler.reset_work_interval()

    def _advance_eye_clock(self) -> None:
        """Count the eye interval and open a card when one falls due.

        The clock runs on the wall rather than on the work interval, because
        eye strain does not pause when the break card is up — it is only that
        a second popup on top of the first teaches you to dismiss both. So a
        card that lands during a break is held over rather than lost.
        """
        settings = self.settings
        if not settings.eye_breaks_enabled:
            self._eye_seconds = 0
            return
        previous = self._eye_seconds
        self._eye_seconds = previous + 1
        if not eyes.eye_due(previous, self._eye_seconds, settings.eye_interval_seconds):
            return
        self._eye_seconds = 0
        self._show_eye_card()

    def _show_eye_card(self) -> None:
        if self.discreet:
            return
        snapshot = self.scheduler.snapshot()
        if snapshot.locked or snapshot.phase in (Phase.BREAK, Phase.AWAITING_RETURN):
            return
        if self.eye_card is not None and self.eye_card.get_visible():
            return
        chosen = eyes.next_prompt(self._eye_index, self.settings.muted_prompts)
        if chosen is None:
            return
        prompt, self._eye_index = chosen
        if self.eye_card is None:
            self.eye_card = EyeWindow(self._eye_squeezed, self._eye_finished)
        self.eye_card.begin(prompt)
        self._play_sound(EYE_CUES["eye_" + prompt.key])

    def _eye_squeezed(self) -> None:
        self._play_sound(EYE_CUES["eye_squeeze"])

    def _eye_finished(self) -> None:
        self._play_sound(EYE_CUES["eye_done"])

    def _refresh_dock(self) -> None:
        if self.dock is None or not self.dock.get_visible():
            return
        snapshot = self.scheduler.snapshot()
        self.dock.update_state(
            snapshot.phase, snapshot.seconds_remaining, snapshot.away_seconds
        )

    def _refresh_standing_pill(self) -> None:
        if self._standing_since is None or self.pill is None:
            return
        seconds = int(self._clock() - self._standing_since)
        cue = standing_cue(self._standing_seconds, seconds)
        self._standing_seconds = seconds
        self.pill.set_seconds(seconds)
        if cue is not None:
            self.pill.pulse(cue)

    def _standing_pill_moved(self, fraction: float) -> None:
        self._save_settings(standing_pill_position=fraction)

    def _reset_work_interval(self, _item) -> None:
        was_awaiting = self.scheduler.snapshot().phase is Phase.AWAITING_RETURN
        if self.scheduler.reset_work_interval():
            if was_awaiting:
                self._record_outcome(BreakOutcome.TAKEN)
                if self.window:
                    self.window.hide()
                    self._hide_dimmers()
            self._update_interface()

    def _pause_reminders(self, _item, seconds: Optional[int]) -> None:
        self.scheduler.pause(seconds)
        self._update_interface()

    def _resume_reminders(self, _item) -> None:
        self.scheduler.resume()
        self._update_interface()

    def _quit_cleanly(self, _item) -> None:
        if self.indicator:
            self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        for dimmer in self._dimmers:
            dimmer.destroy()
        if self.pill:
            self.pill.destroy()
        if self.dock:
            self.dock.destroy()
        if self.eye_card:
            self.eye_card.destroy()
        if self.settings_panel:
            self.settings_panel.destroy()
        if self.control_window:
            self.control_window.destroy()
        if self.stats_window:
            self.stats_window.destroy()
        if self.window:
            self.window.destroy()
        self.quit()


def main(argv: Optional[Sequence[str]] = None) -> int:
    application = ReminderApplication()
    exit_code = application.run(list(argv) if argv is not None else sys.argv)
    return 1 if application.startup_failed else exit_code
