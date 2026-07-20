from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3, Gdk, Gio, GLib, Gtk

from .scheduler import Phase, Scheduler, TimingMode, Transition
from .settings import Settings, SettingsStore


APP_ID = "io.github.abdelali.StandUpReminder"
APP_NAME = "Stand Up Reminder"
ICON_NAME = "stand-up-reminder-symbolic"
DEFAULT_WORK_SECONDS = 30 * 60
DEFAULT_BREAK_SECONDS = 2 * 60


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


@dataclass(frozen=True)
class BreakView:
    title: str
    countdown: str
    away: str
    can_snooze: bool
    can_skip: bool
    can_return: bool


def break_view(
    phase: Phase, seconds_remaining: int, away_seconds: int
) -> BreakView:
    active = phase is Phase.BREAK
    awaiting = phase is Phase.AWAITING_RETURN
    return BreakView(
        title="Break complete" if awaiting else "Time to stand up",
        countdown=format_duration(seconds_remaining),
        away=f"Away for {format_duration(away_seconds)}",
        can_snooze=active,
        can_skip=active,
        can_return=awaiting,
    )


@dataclass(frozen=True)
class IndicatorView:
    status: str
    can_start_break: bool
    can_reset_work: bool


def indicator_view(
    phase: Phase, seconds_remaining: int, away_seconds: int
) -> IndicatorView:
    if phase is Phase.BREAK:
        return IndicatorView("Break in progress", False, False)
    if phase is Phase.SNOOZED:
        return IndicatorView(
            f"Break snoozed for {format_duration(seconds_remaining)}",
            False,
            False,
        )
    if phase is Phase.AWAITING_RETURN:
        return IndicatorView(
            f"Away for {format_duration(away_seconds)}", False, True
        )
    return IndicatorView(
        f"Next break in {format_duration(seconds_remaining)}", True, True
    )


def break_progress_fraction(seconds: int, total_seconds: int) -> float:
    if total_seconds <= 0:
        return 0.0
    return min(1.0, max(0.0, float(seconds) / float(total_seconds)))


class BreakWindow(Gtk.ApplicationWindow):
    def __init__(
        self, application: Gtk.Application, break_seconds: int, on_return
    ) -> None:
        super().__init__(application=application, title="Time to stand up")
        self.break_seconds = break_seconds
        self.set_role("stand-up-break")
        self.set_default_size(440, 350)
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
        self.connect("key-press-event", self._ignore_key)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_border_width(30)
        card.get_style_context().add_class("break-card")

        self.eyebrow = Gtk.Label(label="TIME TO STAND UP")
        self.eyebrow.set_xalign(0.0)
        self.eyebrow.get_style_context().add_class("break-eyebrow")

        self.countdown = Gtk.Label(label=format_duration(break_seconds))
        self.countdown.set_xalign(0.0)
        self.countdown.get_style_context().add_class("break-countdown")

        self.away = Gtk.Label(label="Away for 00:00")
        self.away.set_xalign(0.0)
        self.away.get_style_context().add_class("break-away")

        self.progress = Gtk.ProgressBar()
        self.progress.set_fraction(1.0)
        self.progress.get_style_context().add_class("break-progress")

        prompt = Gtk.Label(
            label="Stand tall. Let your shoulders drop. Take a few steps."
        )
        prompt.set_xalign(0.0)
        prompt.set_line_wrap(True)
        prompt.get_style_context().add_class("break-prompt")

        self.return_button = Gtk.Button(
            label="I'm back \u2014 start 30-minute timer"
        )
        self.return_button.set_no_show_all(True)
        self.return_button.get_style_context().add_class("break-return")
        self.return_button.connect("clicked", on_return)

        card.pack_start(self.eyebrow, False, False, 0)
        card.pack_start(self.countdown, True, True, 0)
        card.pack_start(self.away, False, False, 0)
        card.pack_start(self.progress, False, False, 2)
        card.pack_start(prompt, False, False, 0)
        card.pack_start(self.return_button, False, False, 0)
        self.add(card)

    @staticmethod
    def _ignore_close(*_args) -> bool:
        return True

    @staticmethod
    def _ignore_key(_window, event) -> bool:
        return event.keyval == Gdk.KEY_Escape

    def update_state(
        self, phase: Phase, seconds_remaining: int, away_seconds: int
    ) -> None:
        view = break_view(phase, seconds_remaining, away_seconds)
        self.set_title(view.title)
        self.eyebrow.set_text(view.title.upper())
        self.countdown.set_text(view.countdown)
        self.away.set_text(view.away)
        self.progress.set_fraction(
            break_progress_fraction(seconds_remaining, self.break_seconds)
        )
        self.return_button.set_visible(view.can_return)

    def enforce_front(self) -> None:
        self.set_keep_above(True)
        self.deiconify()
        self.present()


class ReminderApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.scheduler: Optional[Scheduler] = None
        self.window: Optional[BreakWindow] = None
        self.indicator = None
        self.status_item = None
        self.start_item = None
        self.reset_item = None
        self.active_item = None
        self.wall_item = None
        self._settings_store: Optional[SettingsStore] = None
        self._session_bus = None
        self._lock_subscription = 0
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
                color: #c9ddd5;
                font-family: "DejaVu Sans Mono", monospace;
                font-size: 16px;
                font-weight: 600;
            }
            button.break-return {
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
            .break-prompt {
                color: #c9ddd5;
                font-family: Cantarell, sans-serif;
                font-size: 16px;
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
        self._settings_store = SettingsStore(
            config_home / "stand-up-reminder" / "settings.json"
        )
        settings = self._settings_store.load()
        work_seconds = float(
            os.environ.get("STAND_UP_REMINDER_WORK_SECONDS", DEFAULT_WORK_SECONDS)
        )
        break_seconds = float(
            os.environ.get("STAND_UP_REMINDER_BREAK_SECONDS", DEFAULT_BREAK_SECONDS)
        )
        if work_seconds <= 0 or break_seconds <= 0:
            raise ValueError("timer durations must be positive")

        self.scheduler = Scheduler(
            work_seconds=work_seconds,
            break_seconds=break_seconds,
            mode=settings.mode,
        )
        self.window = BreakWindow(self, int(break_seconds), self._confirm_return)
        self._build_indicator(settings.mode)
        self._connect_lock_monitor()
        GLib.timeout_add(250, self._tick)
        self._update_interface()

    def _build_indicator(self, mode: TimingMode) -> None:
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            APP_ID,
            ICON_NAME,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_NAME)
        self.indicator.set_icon_full(ICON_NAME, APP_NAME)

        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="Next break in 30:00")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        self.start_item = Gtk.MenuItem(label="Start break now")
        self.start_item.connect("activate", self._start_break_now)
        menu.append(self.start_item)
        self.reset_item = Gtk.MenuItem(
            label="I'm back — restart 30-minute timer"
        )
        self.reset_item.connect("activate", self._reset_work_interval)
        menu.append(self.reset_item)
        menu.append(Gtk.SeparatorMenuItem())

        timing_item = Gtk.MenuItem(label="Sleep and lock timing")
        timing_menu = Gtk.Menu()
        self.active_item = Gtk.RadioMenuItem.new_with_label(
            None, "Active time only"
        )
        self.wall_item = Gtk.RadioMenuItem.new_with_label_from_widget(
            self.active_item, "Wall-clock time"
        )
        self.active_item.set_active(mode is TimingMode.ACTIVE)
        self.wall_item.set_active(mode is TimingMode.WALL)
        self.active_item.connect(
            "toggled", self._timing_mode_changed, TimingMode.ACTIVE
        )
        self.wall_item.connect(
            "toggled", self._timing_mode_changed, TimingMode.WALL
        )
        timing_menu.append(self.active_item)
        timing_menu.append(self.wall_item)
        timing_item.set_submenu(timing_menu)
        menu.append(timing_item)
        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._quit_cleanly)
        menu.append(quit_item)
        menu.show_all()
        self.indicator.set_menu(menu)

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
        self._apply_transition(transition)
        if (
            not locked
            and transition is not Transition.START_BREAK
            and self.scheduler.snapshot().phase
            in (Phase.BREAK, Phase.AWAITING_RETURN)
        ):
            self._show_break()
        self._update_interface()

    def _tick(self) -> bool:
        transition = self.scheduler.advance()
        self._apply_transition(transition)
        self._update_interface()
        return GLib.SOURCE_CONTINUE

    def _apply_transition(self, transition: Optional[Transition]) -> None:
        if transition is Transition.START_BREAK:
            self._show_break()
        elif transition is Transition.END_BREAK and self.window:
            self.window.hide()

    def _show_break(self) -> None:
        snapshot = self.scheduler.snapshot()
        if snapshot.locked:
            return
        self.window.update_state(
            snapshot.phase,
            snapshot.seconds_remaining,
            snapshot.away_seconds,
        )
        self.window.show_all()
        self.window.enforce_front()

    def _update_interface(self) -> None:
        snapshot = self.scheduler.snapshot()
        if snapshot.phase is Phase.BREAK:
            self.status_item.set_label("Break in progress")
            self.start_item.set_sensitive(False)
            self.reset_item.set_sensitive(False)
        elif snapshot.phase is Phase.AWAITING_RETURN:
            self.status_item.set_label(
                f"Away for {format_duration(snapshot.away_seconds)}"
            )
            self.start_item.set_sensitive(False)
            self.reset_item.set_sensitive(True)
        else:
            self.status_item.set_label(
                f"Next break in {format_duration(snapshot.seconds_remaining)}"
            )
            self.start_item.set_sensitive(True)
            self.reset_item.set_sensitive(True)

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

    def _start_break_now(self, _item) -> None:
        self._apply_transition(self.scheduler.start_break())
        self._update_interface()

    def _confirm_return(self, _button) -> None:
        self._apply_transition(self.scheduler.confirm_return())
        self._update_interface()

    def _reset_work_interval(self, _item) -> None:
        was_awaiting = (
            self.scheduler.snapshot().phase is Phase.AWAITING_RETURN
        )
        if self.scheduler.reset_work_interval():
            if was_awaiting and self.window:
                self.window.hide()
            self._update_interface()

    def _timing_mode_changed(self, item, mode: TimingMode) -> None:
        if not item.get_active() or not self.scheduler:
            return
        transition = self.scheduler.set_mode(mode)
        self._apply_transition(transition)
        try:
            self._settings_store.save(Settings(mode))
        except OSError as error:
            print(
                f"stand-up-reminder: could not save settings: {error}",
                file=sys.stderr,
            )
        self._update_interface()

    def _quit_cleanly(self, _item) -> None:
        if self.indicator:
            self.indicator.set_status(
                AyatanaAppIndicator3.IndicatorStatus.PASSIVE
            )
        if self.window:
            self.window.destroy()
        self.quit()


def main(argv: Optional[Sequence[str]] = None) -> int:
    application = ReminderApplication()
    exit_code = application.run(list(argv) if argv is not None else sys.argv)
    return 1 if application.startup_failed else exit_code
