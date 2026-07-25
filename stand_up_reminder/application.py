from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime
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

from .i18n import _, ngettext
from .scheduler import Phase, Scheduler, TimingMode, Transition
from .settings import (
    BREAK_PRESETS,
    IDLE_CREDIT_PRESETS,
    WORK_PRESETS,
    Settings,
    SettingsStore,
)
from .stats import (
    WEEK_DAYS,
    BreakOutcome,
    DailyStats,
    StatsStore,
    adherence_percent,
    aggregate_stats,
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
IDLE_POLL_SECONDS = 5
PAUSE_PRESETS = (30 * 60, 60 * 60)

# One dot color per recorded outcome, on the break-card palette.
TIMELINE_COLORS = {
    "taken": "#7bc47f",
    "away": "#8fb3a9",
    "missed": "#e05d5d",
    "skipped": "#f2a65a",
    "snoozed": "#c9ddd5",
}
TIMELINE_TRACK_COLOR = "#18312e"


def hex_rgb(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


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


@dataclass(frozen=True)
class BreakView:
    title: str
    countdown: str
    away: str
    can_snooze: bool
    can_skip: bool
    can_return: bool
    can_miss: bool = False


def break_view(phase: Phase, seconds_remaining: int, away_seconds: int) -> BreakView:
    # A work phase means the window is counting down to the break itself.
    if phase is Phase.WORK:
        return BreakView(
            title=_("Break coming up"),
            countdown=format_duration(seconds_remaining),
            away=_("Time to stand up in %s") % format_duration(seconds_remaining),
            can_snooze=False,
            can_skip=False,
            can_return=False,
        )
    active = phase is Phase.BREAK
    awaiting = phase is Phase.AWAITING_RETURN
    return BreakView(
        title=_("Break complete") if awaiting else _("Time to stand up"),
        countdown=format_duration(seconds_remaining),
        away=_("Away for %s") % format_duration(away_seconds),
        can_snooze=active,
        can_skip=active,
        can_return=awaiting,
        can_miss=awaiting,
    )


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
            _("Away for %s") % format_duration(away_seconds), False, True
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


def break_progress_fraction(seconds: int, total_seconds: int) -> float:
    if total_seconds <= 0:
        return 0.0
    return min(1.0, max(0.0, float(seconds) / float(total_seconds)))


class TimelineStrip(Gtk.DrawingArea):
    """A horizontal day track with one colored dot per recorded outcome."""

    def __init__(self, height: int = 26, dot_radius: float = 5.0) -> None:
        super().__init__()
        self._points: list[tuple[float, str]] = []
        self._dot_radius = dot_radius
        self.set_size_request(-1, height)
        self.connect("draw", self._on_draw)

    def set_points(self, points: Sequence[tuple[float, str]]) -> None:
        self._points = list(points)
        self.queue_draw()

    def _on_draw(self, _area, context) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        margin = self._dot_radius + 3
        track = width - 2 * margin
        if track <= 0:
            return False
        middle = height / 2
        context.set_line_width(4)
        context.set_line_cap(1)  # cairo.LINE_CAP_ROUND
        context.set_source_rgb(*hex_rgb(TIMELINE_TRACK_COLOR))
        context.move_to(margin, middle)
        context.line_to(width - margin, middle)
        context.stroke()
        for fraction, outcome in self._points:
            color = TIMELINE_COLORS.get(outcome)
            if color is None:
                continue
            context.set_source_rgb(*hex_rgb(color))
            context.arc(
                margin + fraction * track, middle, self._dot_radius, 0, 6.2832
            )
            context.fill()
        return False


class DimmerWindow(Gtk.Window):
    """A dark cover for monitors that are not showing the break card."""

    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_type_hint(Gdk.WindowTypeHint.SPLASHSCREEN)
        self.stick()
        self.get_style_context().add_class("break-dimmer")
        self.connect("delete-event", lambda *_args: True)

    def cover_monitor(self, monitor_index: int) -> None:
        screen = self.get_screen()
        if screen is None:
            return
        self.fullscreen_on_monitor(screen, monitor_index)


class BreakWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        application: Gtk.Application,
        break_seconds: int,
        on_snooze,
        on_skip,
        on_return,
        on_miss,
        wayland: bool = False,
    ) -> None:
        super().__init__(application=application, title=_("Time to stand up"))
        self.break_seconds = break_seconds
        self.warning_seconds = 0
        self._wayland = wayland
        self.set_role("stand-up-break")
        self.set_default_size(440, 380)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_urgency_hint(True)
        self.stick()
        self.get_style_context().add_class("break-window")
        self.connect("delete-event", self._ignore_close)
        self.connect("key-press-event", self._on_key_press)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_border_width(30)
        card.get_style_context().add_class("break-card")

        self.eyebrow = Gtk.Label(label=_("Time to stand up").upper())
        self.eyebrow.set_xalign(0.0)
        self.eyebrow.get_style_context().add_class("break-eyebrow")

        self.countdown = Gtk.Label(label=format_duration(break_seconds))
        self.countdown.set_xalign(0.0)
        self.countdown.get_style_context().add_class("break-countdown")

        self.away = Gtk.Label(label=_("Away for %s") % format_duration(0))
        self.away.set_xalign(0.0)
        self.away.get_style_context().add_class("break-away")

        self.progress = Gtk.ProgressBar()
        self.progress.set_fraction(1.0)
        self.progress.get_style_context().add_class("break-progress")

        prompt = Gtk.Label(
            label=_("Stand tall. Let your shoulders drop. Take a few steps.")
        )
        prompt.set_xalign(0.0)
        prompt.set_line_wrap(True)
        prompt.get_style_context().add_class("break-prompt")

        self.break_actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )

        # Both action labels name the configured durations; they are replaced
        # by set_snooze_seconds/set_work_seconds once settings are known.
        self.snooze_button = Gtk.Button(label=_("Snooze"))
        self.snooze_button.set_hexpand(True)
        self.snooze_button.set_no_show_all(True)
        self.snooze_button.get_style_context().add_class("break-snooze")
        self.snooze_button.connect("clicked", on_snooze)

        self.skip_button = Gtk.Button(label=_("Skip this break"))
        self.skip_button.set_hexpand(True)
        self.skip_button.set_no_show_all(True)
        self.skip_button.get_style_context().add_class("break-skip")
        self.skip_button.connect("clicked", on_skip)

        self.break_actions.pack_start(self.snooze_button, True, True, 0)
        self.break_actions.pack_start(self.skip_button, True, True, 0)

        self.return_actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )

        self.return_button = Gtk.Button(
            label=_("I'm back — start the work timer")
        )
        self.return_button.set_hexpand(True)
        self.return_button.set_no_show_all(True)
        self.return_button.get_style_context().add_class("break-return")
        self.return_button.connect("clicked", on_return)

        self.miss_button = Gtk.Button(label=_("I didn't take this break"))
        self.miss_button.set_hexpand(True)
        self.miss_button.set_no_show_all(True)
        self.miss_button.get_style_context().add_class("break-skip")
        self.miss_button.connect("clicked", on_miss)

        self.return_actions.pack_start(self.return_button, True, True, 0)
        self.return_actions.pack_start(self.miss_button, True, True, 0)

        self.shortcuts = Gtk.Label()
        self.shortcuts.set_xalign(0.0)
        self.shortcuts.get_style_context().add_class("break-shortcuts")

        self.scores = Gtk.Label()
        self.scores.set_xalign(0.0)
        self.scores.get_style_context().add_class("break-scores")

        self.timeline = TimelineStrip()
        self.timeline.set_no_show_all(True)

        card.pack_start(self.eyebrow, False, False, 0)
        card.pack_start(self.countdown, True, True, 0)
        card.pack_start(self.away, False, False, 0)
        card.pack_start(self.progress, False, False, 2)
        card.pack_start(prompt, False, False, 0)
        card.pack_start(self.break_actions, False, False, 0)
        card.pack_start(self.return_actions, False, False, 0)
        card.pack_start(self.timeline, False, False, 0)
        card.pack_start(self.scores, False, False, 0)
        card.pack_start(self.shortcuts, False, False, 0)
        self.add(card)

    def set_break_seconds(self, break_seconds: int) -> None:
        self.break_seconds = break_seconds

    def set_warning_seconds(self, warning_seconds: int) -> None:
        self.warning_seconds = warning_seconds

    def set_scores(self, text: str) -> None:
        self.scores.set_text(text)

    def set_timeline(self, points: Sequence[tuple[float, str]]) -> None:
        self.timeline.set_points(points)
        # A day without recorded outcomes shows no track at all rather
        # than a bare line that reads as a divider.
        self.timeline.set_visible(bool(points))

    def set_snooze_seconds(self, snooze_seconds: int) -> None:
        self.snooze_button.set_label(
            _("Give me %s") % duration_label(snooze_seconds)
        )

    def set_work_seconds(self, work_seconds: int) -> None:
        self.return_button.set_label(
            _("I'm back — start %s timer") % duration_label(work_seconds)
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
        self.eyebrow.set_text(view.title.upper())
        self.countdown.set_text(view.countdown)
        self.away.set_text(view.away)
        total = self.warning_seconds if phase is Phase.WORK else self.break_seconds
        self.progress.set_fraction(
            break_progress_fraction(seconds_remaining, total)
        )
        self.snooze_button.set_visible(view.can_snooze)
        self.skip_button.set_visible(view.can_skip)
        self.return_button.set_visible(view.can_return)
        self.miss_button.set_visible(view.can_miss)
        if view.can_return:
            shortcuts = _("Enter to confirm")
        elif view.can_snooze:
            shortcuts = _("S to snooze · K to skip")
        else:
            shortcuts = ""
        self.shortcuts.set_text(shortcuts)

    def enforce_front(self) -> None:
        self.set_keep_above(True)
        self.deiconify()
        if self._wayland:
            # Wayland ignores keep-above and explicit placement, so the break
            # card claims the screen instead of being positioned over it.
            self.fullscreen()
        self.present()


class StatsWindow(Gtk.Window):
    """A closable statistics card in the visual language of the break card."""

    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title=_("Statistics"))
        self.set_default_size(560, 540)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.get_style_context().add_class("break-window")
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key_press)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_border_width(30)
        card.get_style_context().add_class("break-card")

        eyebrow = Gtk.Label(label=_("Statistics").upper())
        eyebrow.set_xalign(0.0)
        eyebrow.get_style_context().add_class("break-eyebrow")

        self.score_caption = Gtk.Label(label=_("This week"))
        self.score_caption.set_xalign(0.0)
        self.score_caption.get_style_context().add_class("stats-day-name")

        self.score = Gtk.Label(label="")
        self.score.set_xalign(0.0)
        self.score.get_style_context().add_class("stats-score")

        self.verdict = Gtk.Label(label="")
        self.verdict.set_xalign(0.0)
        self.verdict.set_line_wrap(True)
        self.verdict.get_style_context().add_class("break-away")

        self.today_score = Gtk.Label(label="")
        self.today_score.set_xalign(0.0)
        self.today_score.get_style_context().add_class("break-scores")

        self.timeline = TimelineStrip(height=34, dot_radius=6.0)
        self.timeline.set_no_show_all(True)

        hours = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.timeline_start = Gtk.Label(label="")
        self.timeline_start.set_xalign(0.0)
        self.timeline_start.set_hexpand(True)
        self.timeline_start.get_style_context().add_class("stats-day-name")
        self.timeline_end = Gtk.Label(label="")
        self.timeline_end.set_xalign(1.0)
        self.timeline_end.get_style_context().add_class("stats-day-name")
        hours.pack_start(self.timeline_start, True, True, 0)
        hours.pack_start(self.timeline_end, True, True, 0)
        # The children are shown once here: show_all() is a no-op on a
        # widget that carries no-show-all, so only the box is toggled.
        self.timeline_start.show()
        self.timeline_end.show()
        hours.set_no_show_all(True)
        self.timeline_hours = hours

        legend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        for outcome, word in (
            ("taken", _("taken")),
            ("away", _("away")),
            ("missed", _("missed")),
            ("skipped", _("skipped")),
            ("snoozed", _("snoozed")),
        ):
            entry = Gtk.Label()
            entry.set_markup(
                f'<span foreground="{TIMELINE_COLORS[outcome]}">●</span> {word}'
            )
            entry.get_style_context().add_class("stats-day-name")
            entry.show()
            legend.pack_start(entry, False, False, 0)
        legend.set_no_show_all(True)
        self.timeline_legend = legend

        self.days_grid = Gtk.Grid()
        self.days_grid.set_column_homogeneous(True)
        self.days_grid.set_column_spacing(8)
        self.days_grid.set_row_spacing(2)

        self.today_line = Gtk.Label(label="")
        self.today_line.set_xalign(0.0)
        self.today_line.set_line_wrap(True)
        self.today_line.get_style_context().add_class("break-prompt")

        self.week_line = Gtk.Label(label="")
        self.week_line.set_xalign(0.0)
        self.week_line.set_line_wrap(True)
        self.week_line.get_style_context().add_class("break-prompt")

        close_button = Gtk.Button(label=_("Close"))
        close_button.get_style_context().add_class("break-return")
        close_button.connect("clicked", lambda *_args: self.hide())

        card.pack_start(eyebrow, False, False, 0)
        card.pack_start(self.score_caption, False, False, 0)
        card.pack_start(self.score, False, False, 0)
        card.pack_start(self.verdict, False, False, 0)
        card.pack_start(self.today_score, False, False, 0)
        card.pack_start(self.timeline, False, False, 4)
        card.pack_start(self.timeline_hours, False, False, 0)
        card.pack_start(self.timeline_legend, False, False, 0)
        card.pack_start(self.days_grid, False, False, 8)
        card.pack_start(self.today_line, False, False, 0)
        card.pack_start(self.week_line, False, False, 0)
        card.pack_start(close_button, False, False, 6)
        self.add(card)

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
        week: Sequence[tuple[str, DailyStats]],
        timeline: tuple[int, int, list[tuple[float, str]]],
    ) -> None:
        """Refresh from the week's day keys and stats, today last."""
        start_minutes, end_minutes, points = timeline
        self.timeline.set_points(points)
        self.timeline_start.set_text(
            f"{start_minutes // 60:02d}:{start_minutes % 60:02d}"
        )
        self.timeline_end.set_text(
            f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
        )
        # The whole timeline block appears only once the day has dots.
        if points:
            self.timeline.show()
            self.timeline_hours.show()
            self.timeline_legend.show()
        else:
            self.timeline.hide()
            self.timeline_hours.hide()
            self.timeline_legend.hide()
        today_stats = week[-1][1] if week else DailyStats()
        week_total = aggregate_stats(stats for _day, stats in week)
        percent = adherence_percent(week_total)
        self.score.set_text(score_headline(percent))
        self.verdict.set_text(rating_label(percent))
        self.today_score.set_text(
            _("Today: %s") % score_headline(adherence_percent(today_stats))
        )
        self.today_line.set_text(summary_label(today_stats))
        self.week_line.set_text(week_label(week_total))

        for child in self.days_grid.get_children():
            child.destroy()
        for column, (day, stats) in enumerate(week):
            name = Gtk.Label(label=date.fromisoformat(day).strftime("%a"))
            name.get_style_context().add_class("stats-day-name")
            count = Gtk.Label(label=str(stats.taken))
            count.get_style_context().add_class("stats-day-count")
            self.days_grid.attach(name, column, 0, 1, 1)
            self.days_grid.attach(count, column, 1, 1, 1)
        self.days_grid.show_all()


class ReminderApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.scheduler: Optional[Scheduler] = None
        self.window: Optional[BreakWindow] = None
        self.stats_window: Optional[StatsWindow] = None
        self.settings = Settings()
        self.indicator = None
        self.stats = None
        self.status_item = None
        self.stats_item = None
        self.start_item = None
        self.reset_item = None
        self.resume_item = None
        self.pause_item = None
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
        self._stats_day = ""
        self._stats_summary = ""
        self._score_day = ""
        self._indicator_label = None
        self._idle_credit_pending = False
        self._suppress_menu_events = False
        self._wayland = False
        self._started = False
        self.startup_failed = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window.break-window,
            .break-card {
                background-color: #294c47;
                color: #e9f2ed;
            }
            window.break-dimmer {
                background-color: #18312e;
            }
            .break-eyebrow {
                color: #f2a65a;
                font-family: Cantarell, sans-serif;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            .break-countdown {
                color: #f7f2e7;
                font-family: "DejaVu Sans Mono", monospace;
                font-size: 74px;
                font-weight: 700;
            }
            .break-away {
                color: #f2a65a;
                font-family: "DejaVu Sans Mono", monospace;
                font-size: 21px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            button.break-return,
            button.break-snooze {
                min-height: 38px;
                border: 1px solid #f2a65a;
                background-image: none;
                border-radius: 6px;
                color: #18312e;
                background-color: #f2a65a;
                box-shadow: none;
                font-family: Cantarell, sans-serif;
                font-size: 15px;
                font-weight: 700;
            }
            button.break-skip {
                min-height: 38px;
                border: 1px solid #c9ddd5;
                background-image: none;
                border-radius: 6px;
                color: #e9f2ed;
                background-color: #294c47;
                box-shadow: none;
                font-family: Cantarell, sans-serif;
                font-size: 15px;
                font-weight: 700;
            }
            .break-prompt {
                color: #c9ddd5;
                font-family: Cantarell, sans-serif;
                font-size: 16px;
            }
            .break-scores {
                color: #c9ddd5;
                font-family: Cantarell, sans-serif;
                font-size: 13px;
                letter-spacing: 1px;
            }
            .stats-score {
                color: #f7f2e7;
                font-family: "DejaVu Sans Mono", monospace;
                font-size: 52px;
                font-weight: 700;
            }
            .stats-day-name {
                color: #8fb3a9;
                font-family: Cantarell, sans-serif;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            .stats-day-count {
                color: #f7f2e7;
                font-family: "DejaVu Sans Mono", monospace;
                font-size: 22px;
                font-weight: 700;
            }
            .break-shortcuts {
                color: #8fb3a9;
                font-family: Cantarell, sans-serif;
                font-size: 12px;
                letter-spacing: 1px;
            }
            progressbar.break-progress trough {
                min-height: 8px;
                border: 0;
                border-radius: 4px;
                background-color: #18312e;
            }
            progressbar.break-progress progress {
                min-height: 8px;
                border: 0;
                border-radius: 4px;
                background-color: #f2a65a;
            }
            """
        )
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
        if GSound is None:
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

        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label=_("Next break in 30:00"))
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        self.stats_item = Gtk.MenuItem(label=_("No breaks yet today"))
        self.stats_item.set_sensitive(False)
        menu.append(self.stats_item)

        stats_page_item = Gtk.MenuItem(label=_("Statistics"))
        stats_page_item.connect("activate", self._open_stats_window)
        menu.append(stats_page_item)
        menu.append(Gtk.SeparatorMenuItem())

        self.start_item = Gtk.MenuItem(label=_("Start break now"))
        self.start_item.connect("activate", self._start_break_now)
        menu.append(self.start_item)
        self.reset_item = Gtk.MenuItem(label=_("I'm back — restart the work timer"))
        self.reset_item.connect("activate", self._reset_work_interval)
        menu.append(self.reset_item)

        self.pause_item = Gtk.MenuItem(label=_("Pause reminders"))
        pause_menu = Gtk.Menu()
        for seconds in PAUSE_PRESETS:
            item = Gtk.MenuItem(label=_("For %s") % duration_label(seconds))
            item.connect("activate", self._pause_reminders, seconds)
            pause_menu.append(item)
        indefinite = Gtk.MenuItem(label=_("Until I resume"))
        indefinite.connect("activate", self._pause_reminders, None)
        pause_menu.append(indefinite)
        self.pause_item.set_submenu(pause_menu)
        menu.append(self.pause_item)

        self.resume_item = Gtk.MenuItem(label=_("Resume reminders"))
        self.resume_item.connect("activate", self._resume_reminders)
        menu.append(self.resume_item)
        menu.append(Gtk.SeparatorMenuItem())

        menu.append(self._build_duration_item())
        menu.append(self._build_timing_item())
        menu.append(self._build_options_item())
        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label=_("Quit"))
        quit_item.connect("activate", self._quit_cleanly)
        menu.append(quit_item)
        menu.show_all()
        self.indicator.set_menu(menu)

    def _build_duration_item(self) -> Gtk.MenuItem:
        durations_item = Gtk.MenuItem(label=_("Durations"))
        durations_menu = Gtk.Menu()

        work_item = Gtk.MenuItem(label=_("Work interval"))
        work_menu = Gtk.Menu()
        group = None
        for seconds in WORK_PRESETS:
            entry = Gtk.RadioMenuItem.new_with_label_from_widget(
                group, duration_label(seconds)
            )
            group = group or entry
            entry.set_active(seconds == self.settings.work_seconds)
            entry.connect("toggled", self._work_seconds_changed, seconds)
            self.work_items[seconds] = entry
            work_menu.append(entry)
        work_item.set_submenu(work_menu)
        durations_menu.append(work_item)

        break_item = Gtk.MenuItem(label=_("Break length"))
        break_menu = Gtk.Menu()
        group = None
        for seconds in BREAK_PRESETS:
            entry = Gtk.RadioMenuItem.new_with_label_from_widget(
                group, duration_label(seconds)
            )
            group = group or entry
            entry.set_active(seconds == self.settings.break_seconds)
            entry.connect("toggled", self._break_seconds_changed, seconds)
            self.break_items[seconds] = entry
            break_menu.append(entry)
        break_item.set_submenu(break_menu)
        durations_menu.append(break_item)

        durations_item.set_submenu(durations_menu)
        return durations_item

    def _build_timing_item(self) -> Gtk.MenuItem:
        timing_item = Gtk.MenuItem(label=_("Sleep and lock timing"))
        timing_menu = Gtk.Menu()
        self.active_item = Gtk.RadioMenuItem.new_with_label(
            None, _("Active time only")
        )
        self.wall_item = Gtk.RadioMenuItem.new_with_label_from_widget(
            self.active_item, _("Wall-clock time")
        )
        self.active_item.set_active(self.settings.mode is TimingMode.ACTIVE)
        self.wall_item.set_active(self.settings.mode is TimingMode.WALL)
        self.active_item.connect(
            "toggled", self._timing_mode_changed, TimingMode.ACTIVE
        )
        self.wall_item.connect("toggled", self._timing_mode_changed, TimingMode.WALL)
        timing_menu.append(self.active_item)
        timing_menu.append(self.wall_item)
        timing_item.set_submenu(timing_menu)
        return timing_item

    def _build_options_item(self) -> Gtk.MenuItem:
        options_item = Gtk.MenuItem(label=_("Options"))
        options_menu = Gtk.Menu()

        self.countdown_item = Gtk.CheckMenuItem(label=_("Show countdown in top bar"))
        self.countdown_item.set_active(self.settings.show_countdown)
        self.countdown_item.connect("toggled", self._countdown_toggled)
        options_menu.append(self.countdown_item)

        self.idle_item = Gtk.CheckMenuItem(label=_("Count time away as a break"))
        self.idle_item.set_active(self.settings.idle_reset_enabled)
        self.idle_item.connect("toggled", self._idle_toggled)
        options_menu.append(self.idle_item)

        idle_credit_item = Gtk.MenuItem(label=_("Count away after"))
        idle_credit_menu = Gtk.Menu()
        group = None
        for seconds in IDLE_CREDIT_PRESETS:
            entry = Gtk.RadioMenuItem.new_with_label_from_widget(
                group, duration_label(seconds)
            )
            group = group or entry
            entry.set_active(seconds == self.settings.idle_credit_seconds)
            entry.connect("toggled", self._idle_credit_seconds_changed, seconds)
            self.idle_credit_items[seconds] = entry
            idle_credit_menu.append(entry)
        idle_credit_item.set_submenu(idle_credit_menu)
        options_menu.append(idle_credit_item)

        self.sound_item = Gtk.CheckMenuItem(label=_("Play a sound at each break"))
        self.sound_item.set_active(self.settings.sound_enabled)
        self.sound_item.connect("toggled", self._sound_toggled)
        options_menu.append(self.sound_item)

        options_item.set_submenu(options_menu)
        return options_item

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
        self._update_interface()
        return GLib.SOURCE_CONTINUE

    def _apply_transition(self, transition: Optional[Transition]) -> None:
        if transition is Transition.WARN_BREAK:
            self._show_warning()
        elif transition is Transition.START_BREAK:
            self._play_sound("message-new-instant")
            self._show_break()
        elif transition is Transition.BREAK_COMPLETE:
            self._play_sound("complete")
        elif transition is Transition.END_BREAK and self.window:
            self.window.hide()
            self._hide_dimmers()

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

    def _play_sound(self, event_id: str) -> None:
        if not self.settings.sound_enabled or self._sound is None:
            return
        try:
            self._sound.play_simple({GSound.ATTR_EVENT_ID: event_id}, None)
        except GLib.Error:  # pragma: no cover - depends on host audio
            pass

    def _show_break(self) -> None:
        snapshot = self.scheduler.snapshot()
        if snapshot.locked:
            return
        self._refresh_score_line()
        self.window.update_state(
            snapshot.phase,
            snapshot.seconds_remaining,
            snapshot.away_seconds,
        )
        self.window.show_all()
        self.window.enforce_front()
        # The break window has to be realized before GDK can report which
        # monitor it landed on.
        self._show_dimmers()

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
        self.start_item.set_sensitive(view.can_start_break)
        self.reset_item.set_sensitive(view.can_reset_work)
        self.pause_item.set_sensitive(view.can_pause)
        self.resume_item.set_sensitive(view.can_resume)
        today = today_key()
        self.stats_item.set_label(self._stats_label(today))
        if self._score_day != today:
            self._refresh_score_line()

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
                self._hide_dimmers()

    def _record_outcome(self, outcome: BreakOutcome) -> None:
        if self.stats is None:
            return
        self.stats.record(outcome)
        self._stats_day = today_key()
        self._stats_summary = summary_label(self.stats.load(self._stats_day))
        self._refresh_score_line()
        if self.stats_window and self.stats_window.get_visible():
            self._refresh_stats_window()

    @staticmethod
    def _now_minutes() -> int:
        now = datetime.now()
        return now.hour * 60 + now.minute

    def _today_timeline(self, day: str) -> tuple[int, int, list]:
        return timeline_layout(self.stats.load_events(day), self._now_minutes())

    def _refresh_score_line(self) -> None:
        """Recompute the day and week adherence shown on the break window."""
        if self.stats is None or self.window is None:
            return
        days = last_days(WEEK_DAYS)
        stats_list = self.stats.load_days(days)
        self._score_day = days[-1]
        self.window.set_scores(
            score_line(
                adherence_percent(stats_list[-1]),
                adherence_percent(aggregate_stats(stats_list)),
            )
        )
        self.window.set_timeline(self._today_timeline(days[-1])[2])

    def _open_stats_window(self, _item) -> None:
        if self.stats_window is None:
            self.stats_window = StatsWindow()
        self._refresh_stats_window()
        self.stats_window.show_all()
        self.stats_window.present()

    def _refresh_stats_window(self) -> None:
        if self.stats_window is None or self.stats is None:
            return
        days = last_days(WEEK_DAYS)
        self.stats_window.update_stats(
            list(zip(days, self.stats.load_days(days))),
            self._today_timeline(days[-1]),
        )

    def _stats_label(self, day: str) -> str:
        """Cached daily summary, re-read only when the counters can differ.

        The interface refreshes four times a second, so the stored counters are
        loaded when an outcome is recorded and when the date rolls over rather
        than on every refresh.
        """
        if day != self._stats_day:
            self._stats_day = day
            self._stats_summary = summary_label(self.stats.load(day))
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
        self._apply_transition(transition)
        self._update_interface()

    def _missed_break(self, _button) -> None:
        transition = self.scheduler.confirm_return()
        if transition is Transition.END_BREAK:
            self._record_outcome(BreakOutcome.MISSED)
        self._apply_transition(transition)
        self._update_interface()

    def _snooze_break(self, _button) -> None:
        if self.scheduler.snooze_break():
            self._record_outcome(BreakOutcome.SNOOZED)
            self.window.hide()
            self._hide_dimmers()
        self._update_interface()

    def _skip_break(self, _button) -> None:
        if self.scheduler.skip_break():
            self._record_outcome(BreakOutcome.SKIPPED)
            self.window.hide()
            self._hide_dimmers()
        self._update_interface()

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

    def _work_seconds_changed(self, item, seconds: int) -> None:
        if self._suppress_menu_events or not item.get_active():
            return
        self.scheduler.set_durations(work_seconds=seconds)
        self.window.set_work_seconds(seconds)
        self._save_settings(work_seconds=seconds)
        self._update_interface()

    def _break_seconds_changed(self, item, seconds: int) -> None:
        if self._suppress_menu_events or not item.get_active():
            return
        self.scheduler.set_durations(break_seconds=seconds)
        self.window.set_break_seconds(seconds)
        self._save_settings(break_seconds=seconds)
        self._update_interface()

    def _countdown_toggled(self, item) -> None:
        self._save_settings(show_countdown=item.get_active())
        self._update_interface()

    def _idle_toggled(self, item) -> None:
        self._save_settings(idle_reset_enabled=item.get_active())

    def _idle_credit_seconds_changed(self, item, seconds: int) -> None:
        if self._suppress_menu_events or not item.get_active():
            return
        self._save_settings(idle_credit_seconds=seconds)

    def _sound_toggled(self, item) -> None:
        self._save_settings(sound_enabled=item.get_active())

    def _timing_mode_changed(self, item, mode: TimingMode) -> None:
        if self._suppress_menu_events or not item.get_active() or not self.scheduler:
            return
        transition = self.scheduler.set_mode(mode)
        self._apply_transition(transition)
        self._save_settings(mode=mode)
        self._update_interface()

    def _quit_cleanly(self, _item) -> None:
        if self.indicator:
            self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        for dimmer in self._dimmers:
            dimmer.destroy()
        if self.stats_window:
            self.stats_window.destroy()
        if self.window:
            self.window.destroy()
        self.quit()


def main(argv: Optional[Sequence[str]] = None) -> int:
    application = ReminderApplication()
    exit_code = application.run(list(argv) if argv is not None else sys.argv)
    return 1 if application.startup_failed else exit_code
