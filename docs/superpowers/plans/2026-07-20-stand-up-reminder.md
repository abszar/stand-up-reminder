# Stand Up Reminder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, install, and start a native Ubuntu GNOME reminder that enforces a two-minute standing break after each 30-minute work interval.

**Architecture:** A deterministic scheduler and JSON settings store remain independent of GTK. A small GTK 3 application coordinates the scheduler with a centered always-on-top countdown, an Ayatana AppIndicator menu, and GNOME lock-state D-Bus events. User-level installation uses a systemd service for crash recovery plus an XDG autostart entry for every graphical login.

**Tech Stack:** Python 3.12 standard library, PyGObject 3.48, GTK 3.24, AyatanaAppIndicator3 0.1, Gio/GLib D-Bus, systemd user services, XDG desktop entries, `unittest`.

## Global Constraints

- Target Ubuntu 24.04 with GNOME Shell 46 on X11.
- Use the already-installed Python 3, GTK 3, PyGObject, Ayatana AppIndicator, and Ubuntu AppIndicators GNOME extension.
- Do not require network access or new system packages.
- Install entirely for the current user; administrator access is unnecessary.
- Use fixed intervals: 30 minutes between breaks and 2 minutes per break.
- The countdown must remain centered and above other windows and ignore ordinary close requests, Escape, and Alt+F4.
- Quit must stop reminders until manual relaunch or the next graphical login.
- Never use the prohibited vendor name in commit messages.

---

## File structure

- `stand_up_reminder/scheduler.py`: deterministic work/break state machine and lock/suspend timing policies.
- `stand_up_reminder/settings.py`: validated, atomic JSON persistence for the timing policy.
- `stand_up_reminder/application.py`: GTK window, indicator, GNOME lock listener, and application coordinator.
- `stand_up_reminder/__main__.py`: executable module entry point.
- `stand_up_reminder/__init__.py`: package metadata.
- `tests/test_scheduler.py`: scheduler state-transition tests with fake clocks.
- `tests/test_settings.py`: settings validation and persistence tests.
- `tests/test_application_helpers.py`: display formatting tests that do not require a GUI session.
- `tests/test_install_assets.py`: static validation of desktop, service, icon, and installer assets.
- `data/stand-up-reminder.service`: systemd user service with crash-only restart.
- `data/stand-up-reminder.desktop`: GNOME Applications-menu launcher.
- `data/stand-up-reminder-autostart.desktop`: XDG graphical-login autostart launcher.
- `data/stand-up-reminder-symbolic.svg`: top-bar and Applications-menu icon.
- `scripts/install.sh`: idempotent per-user installation and startup.
- `scripts/uninstall.sh`: idempotent per-user removal.
- `README.md`: behavior, menu, timing modes, installation, and removal.

---

### Task 1: Deterministic scheduler

**Files:**
- Create: `stand_up_reminder/__init__.py`
- Create: `stand_up_reminder/scheduler.py`
- Create: `tests/__init__.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: injected `monotonic() -> float` and `wall_clock() -> float` callables.
- Produces: `Scheduler`, `Phase`, `TimingMode`, `Transition`, and `Snapshot` for the GTK coordinator.

- [ ] **Step 1: Write the scheduler tests**

```python
# tests/test_scheduler.py
import unittest

from stand_up_reminder.scheduler import Phase, Scheduler, TimingMode, Transition


class FakeClocks:
    def __init__(self):
        self.mono = 100.0
        self.wall = 1_000.0

    def monotonic(self):
        return self.mono

    def wall_clock(self):
        return self.wall

    def advance(self, seconds, *, suspended=False):
        self.wall += seconds
        if not suspended:
            self.mono += seconds


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clocks = FakeClocks()
        self.scheduler = Scheduler(
            work_seconds=30,
            break_seconds=2,
            mode=TimingMode.ACTIVE,
            monotonic=self.clocks.monotonic,
            wall_clock=self.clocks.wall_clock,
        )

    def test_initial_work_interval(self):
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 30)

    def test_work_deadline_starts_break(self):
        self.clocks.advance(30)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 2)

    def test_break_completion_resets_full_work_interval(self):
        self.scheduler.start_break()
        self.clocks.advance(2)
        self.assertEqual(self.scheduler.advance(), Transition.END_BREAK)
        self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_manual_start_is_ignored_during_break(self):
        self.assertEqual(self.scheduler.start_break(), Transition.START_BREAK)
        self.assertIsNone(self.scheduler.start_break())

    def test_active_mode_pauses_during_lock(self):
        self.clocks.advance(10)
        self.scheduler.set_locked(True)
        self.clocks.advance(40)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 20)
        self.assertIsNone(self.scheduler.set_locked(False))

    def test_active_mode_excludes_suspend(self):
        self.clocks.advance(40, suspended=True)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_wall_mode_counts_lock_and_starts_on_unlock(self):
        self.scheduler.set_mode(TimingMode.WALL)
        self.scheduler.set_locked(True)
        self.clocks.advance(31)
        self.assertIsNone(self.scheduler.advance())
        self.assertEqual(self.scheduler.set_locked(False), Transition.START_BREAK)

    def test_wall_mode_counts_suspend(self):
        self.scheduler.set_mode(TimingMode.WALL)
        self.clocks.advance(31, suspended=True)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)

    def test_break_pauses_while_locked_for_both_modes(self):
        self.scheduler.set_mode(TimingMode.WALL)
        self.scheduler.start_break()
        self.scheduler.set_locked(True)
        self.clocks.advance(20)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 2)

    def test_policy_change_preserves_remaining_time(self):
        self.clocks.advance(7)
        self.scheduler.set_mode(TimingMode.WALL)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 23)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run: `python3 -m unittest tests.test_scheduler -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'stand_up_reminder'`.

- [ ] **Step 3: Implement the scheduler**

```python
# stand_up_reminder/__init__.py
"""Native GNOME stand-up reminder."""

__version__ = "1.0.0"
```

```python
# stand_up_reminder/scheduler.py
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Phase(str, Enum):
    WORK = "work"
    BREAK = "break"


class TimingMode(str, Enum):
    ACTIVE = "active"
    WALL = "wall"


class Transition(str, Enum):
    START_BREAK = "start_break"
    END_BREAK = "end_break"


@dataclass(frozen=True)
class Snapshot:
    phase: Phase
    seconds_remaining: int
    locked: bool
    mode: TimingMode


class Scheduler:
    def __init__(
        self,
        *,
        work_seconds: float = 30 * 60,
        break_seconds: float = 2 * 60,
        mode: TimingMode = TimingMode.ACTIVE,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.work_seconds = float(work_seconds)
        self.break_seconds = float(break_seconds)
        self.mode = TimingMode(mode)
        self.phase = Phase.WORK
        self.remaining = self.work_seconds
        self.locked = False
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._last_mono = monotonic()
        self._last_wall = wall_clock()

    def _elapsed(self) -> tuple[float, float]:
        now_mono = self._monotonic()
        now_wall = self._wall_clock()
        mono_delta = max(0.0, now_mono - self._last_mono)
        wall_delta = max(0.0, now_wall - self._last_wall)
        self._last_mono = now_mono
        self._last_wall = now_wall
        return mono_delta, wall_delta

    def advance(self) -> Optional[Transition]:
        mono_delta, wall_delta = self._elapsed()

        if self.locked:
            if self.phase is Phase.WORK and self.mode is TimingMode.WALL:
                self.remaining = max(0.0, self.remaining - wall_delta)
            return None

        delta = mono_delta
        if self.phase is Phase.WORK and self.mode is TimingMode.WALL:
            delta = wall_delta
        self.remaining = max(0.0, self.remaining - delta)

        if self.remaining > 0:
            return None
        if self.phase is Phase.WORK:
            self.phase = Phase.BREAK
            self.remaining = self.break_seconds
            return Transition.START_BREAK

        self.phase = Phase.WORK
        self.remaining = self.work_seconds
        return Transition.END_BREAK

    def start_break(self) -> Optional[Transition]:
        self.advance()
        if self.phase is Phase.BREAK:
            return None
        self.phase = Phase.BREAK
        self.remaining = self.break_seconds
        return Transition.START_BREAK

    def set_locked(self, locked: bool) -> Optional[Transition]:
        transition = self.advance()
        self.locked = bool(locked)
        if not self.locked:
            return self.advance() or transition
        return transition

    def set_mode(self, mode: TimingMode) -> None:
        self.advance()
        self.mode = TimingMode(mode)

    def snapshot(self) -> Snapshot:
        return Snapshot(
            phase=self.phase,
            seconds_remaining=int(math.ceil(max(0.0, self.remaining))),
            locked=self.locked,
            mode=self.mode,
        )
```

- [ ] **Step 4: Run scheduler tests**

Run: `python3 -m unittest tests.test_scheduler -v`

Expected: 10 tests pass.

- [ ] **Step 5: Commit the scheduler**

```bash
git add stand_up_reminder/__init__.py stand_up_reminder/scheduler.py tests/__init__.py tests/test_scheduler.py
git commit -m "feat: add deterministic break scheduler"
```

---

### Task 2: Validated settings persistence

**Files:**
- Create: `stand_up_reminder/settings.py`
- Create: `tests/test_settings.py`

**Interfaces:**
- Consumes: `TimingMode` from `stand_up_reminder.scheduler`.
- Produces: `Settings(mode: TimingMode)` and `SettingsStore.load()/save()`.

- [ ] **Step 1: Write settings tests**

```python
# tests/test_settings.py
import json
import tempfile
import unittest
from pathlib import Path

from stand_up_reminder.scheduler import TimingMode
from stand_up_reminder.settings import Settings, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "nested" / "settings.json"
        self.store = SettingsStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_file_uses_active_default(self):
        self.assertEqual(self.store.load(), Settings(TimingMode.ACTIVE))

    def test_malformed_file_uses_active_default(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(self.store.load(), Settings(TimingMode.ACTIVE))

    def test_unknown_mode_uses_active_default(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"timing_mode": "unknown"}), encoding="utf-8")
        self.assertEqual(self.store.load(), Settings(TimingMode.ACTIVE))

    def test_save_round_trip(self):
        self.store.save(Settings(TimingMode.WALL))
        self.assertEqual(self.store.load(), Settings(TimingMode.WALL))
        self.assertFalse(self.path.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run: `python3 -m unittest tests.test_settings -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'stand_up_reminder.settings'`.

- [ ] **Step 3: Implement the settings store**

```python
# stand_up_reminder/settings.py
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .scheduler import TimingMode


@dataclass(frozen=True)
class Settings:
    mode: TimingMode = TimingMode.ACTIVE


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return Settings(mode=TimingMode(payload["timing_mode"]))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            if self.path.exists():
                print(f"stand-up-reminder: using default settings: {error}", file=sys.stderr)
            return Settings()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps({"timing_mode": settings.mode.value}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            finally:
                raise
```

- [ ] **Step 4: Run all domain tests**

Run: `python3 -m unittest tests.test_scheduler tests.test_settings -v`

Expected: 14 tests pass.

- [ ] **Step 5: Commit settings persistence**

```bash
git add stand_up_reminder/settings.py tests/test_settings.py
git commit -m "feat: persist reminder timing policy"
```

---

### Task 3: Native GTK application and top-bar indicator

**Files:**
- Create: `stand_up_reminder/application.py`
- Create: `stand_up_reminder/__main__.py`
- Create: `tests/test_application_helpers.py`

**Interfaces:**
- Consumes: `Scheduler`, `Transition`, `Phase`, `TimingMode`, `Settings`, and `SettingsStore`.
- Produces: `format_duration(seconds: int) -> str`, `BreakWindow`, `ReminderApplication`, and `main(argv=None) -> int`.

- [ ] **Step 1: Write headless application-helper tests**

```python
# tests/test_application_helpers.py
import unittest

from stand_up_reminder.application import format_duration


class FormatDurationTests(unittest.TestCase):
    def test_formats_minutes_and_seconds(self):
        self.assertEqual(format_duration(120), "02:00")
        self.assertEqual(format_duration(61), "01:01")
        self.assertEqual(format_duration(0), "00:00")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the helper test and verify the expected failure**

Run: `python3 -m unittest tests.test_application_helpers -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'stand_up_reminder.application'`.

- [ ] **Step 3: Implement the GTK application**

```python
# stand_up_reminder/application.py
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3, Gdk, Gio, GLib, Gtk

from .scheduler import Phase, Scheduler, TimingMode, Transition
from .settings import Settings, SettingsStore


APP_ID = "io.github.abdelali.StandUpReminder"
ICON_NAME = "stand-up-reminder-symbolic"


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


class BreakWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="Time to stand up")
        self.set_default_size(420, 250)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.stick()
        self.connect("delete-event", self._ignore_close)
        self.connect("key-press-event", self._ignore_escape)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.set_border_width(28)
        card.get_style_context().add_class("break-card")

        title = Gtk.Label(label="Time to stand up")
        title.get_style_context().add_class("break-title")
        self.countdown = Gtk.Label(label="02:00")
        self.countdown.get_style_context().add_class("break-countdown")
        prompt = Gtk.Label(label="Stand, stretch, and move for two minutes.")
        prompt.get_style_context().add_class("break-prompt")

        card.pack_start(title, False, False, 0)
        card.pack_start(self.countdown, True, True, 0)
        card.pack_start(prompt, False, False, 0)
        self.add(card)

    @staticmethod
    def _ignore_close(*_args) -> bool:
        return True

    @staticmethod
    def _ignore_escape(_window, event) -> bool:
        return event.keyval == Gdk.KEY_Escape

    def set_seconds(self, seconds: int) -> None:
        self.countdown.set_text(format_duration(seconds))

    def enforce_front(self) -> None:
        self.set_keep_above(True)
        self.present()


class ReminderApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.scheduler: Optional[Scheduler] = None
        self.window: Optional[BreakWindow] = None
        self.indicator = None
        self.status_item = None
        self.start_item = None
        self.active_item = None
        self.wall_item = None
        self._settings_store: Optional[SettingsStore] = None
        self._lock_subscription = 0
        self._started = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background: #111827; color: #f9fafb; }
            .break-card { background: #111827; }
            .break-title { font-size: 25px; font-weight: 700; }
            .break-countdown { font-size: 72px; font-weight: 700; color: #67e8f9; }
            .break-prompt { font-size: 16px; color: #d1d5db; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self) -> None:
        if self._started:
            if self.scheduler and self.scheduler.snapshot().phase is Phase.BREAK:
                self._show_break()
            return

        self._started = True
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self._settings_store = SettingsStore(
            config_home / "stand-up-reminder" / "settings.json"
        )
        settings = self._settings_store.load()
        work_seconds = float(os.environ.get("STAND_UP_REMINDER_WORK_SECONDS", "1800"))
        break_seconds = float(os.environ.get("STAND_UP_REMINDER_BREAK_SECONDS", "120"))
        self.scheduler = Scheduler(
            work_seconds=work_seconds,
            break_seconds=break_seconds,
            mode=settings.mode,
        )
        self.window = BreakWindow(self)
        self._build_indicator(settings.mode)
        self._connect_lock_monitor()
        GLib.timeout_add_seconds(1, self._tick)
        self._update_interface()

    def _build_indicator(self, mode: TimingMode) -> None:
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            APP_ID,
            ICON_NAME,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Stand Up Reminder")

        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="Next break in 30:00")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        self.start_item = Gtk.MenuItem(label="Start break now")
        self.start_item.connect("activate", self._start_break_now)
        menu.append(self.start_item)
        menu.append(Gtk.SeparatorMenuItem())

        timing_item = Gtk.MenuItem(label="Sleep and lock timing")
        timing_menu = Gtk.Menu()
        self.active_item = Gtk.RadioMenuItem.new_with_label(None, "Active time only")
        self.wall_item = Gtk.RadioMenuItem.new_with_label_from_widget(
            self.active_item, "Wall-clock time"
        )
        self.active_item.set_active(mode is TimingMode.ACTIVE)
        self.wall_item.set_active(mode is TimingMode.WALL)
        self.active_item.connect("toggled", self._timing_mode_changed, TimingMode.ACTIVE)
        self.wall_item.connect("toggled", self._timing_mode_changed, TimingMode.WALL)
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
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._lock_subscription = bus.signal_subscribe(
            "org.gnome.ScreenSaver",
            "org.gnome.ScreenSaver",
            "ActiveChanged",
            "/org/gnome/ScreenSaver",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_lock_signal,
        )
        reply = bus.call_sync(
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

    def _on_lock_signal(self, _bus, _sender, _path, _interface, _signal, parameters) -> None:
        self._set_locked(parameters.unpack()[0])

    def _set_locked(self, locked: bool) -> None:
        transition = self.scheduler.set_locked(locked)
        if locked and self.window:
            self.window.hide()
        elif not locked and self.scheduler.snapshot().phase is Phase.BREAK:
            self._show_break()
        self._apply_transition(transition)

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
        if self.scheduler.snapshot().locked:
            return
        self.window.set_seconds(self.scheduler.snapshot().seconds_remaining)
        self.window.show_all()
        self.window.enforce_front()

    def _update_interface(self) -> None:
        snapshot = self.scheduler.snapshot()
        if snapshot.phase is Phase.BREAK:
            self.status_item.set_label("Break in progress")
            self.start_item.set_sensitive(False)
            if not snapshot.locked:
                self.window.set_seconds(snapshot.seconds_remaining)
                self.window.enforce_front()
        else:
            self.status_item.set_label(
                f"Next break in {format_duration(snapshot.seconds_remaining)}"
            )
            self.start_item.set_sensitive(True)

    def _start_break_now(self, _item) -> None:
        self._apply_transition(self.scheduler.start_break())
        self._update_interface()

    def _timing_mode_changed(self, item, mode: TimingMode) -> None:
        if not item.get_active() or not self.scheduler:
            return
        self.scheduler.set_mode(mode)
        try:
            self._settings_store.save(Settings(mode))
        except OSError as error:
            print(f"stand-up-reminder: could not save settings: {error}", file=sys.stderr)
        self._update_interface()

    def _quit_cleanly(self, _item) -> None:
        if self.indicator:
            self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        if self.window:
            self.window.destroy()
        self.quit()


def main(argv: Optional[Sequence[str]] = None) -> int:
    application = ReminderApplication()
    return application.run(list(argv) if argv is not None else sys.argv)
```

```python
# stand_up_reminder/__main__.py
from .application import main

raise SystemExit(main())
```

- [ ] **Step 4: Run the complete Python test suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: 15 tests pass.

- [ ] **Step 5: Smoke-test imports against installed GUI bindings**

Run: `python3 -c "from stand_up_reminder.application import ReminderApplication; print(ReminderApplication.__name__)"`

Expected: prints `ReminderApplication` with exit code 0.

- [ ] **Step 6: Commit the native application**

```bash
git add stand_up_reminder/application.py stand_up_reminder/__main__.py tests/test_application_helpers.py
git commit -m "feat: add native countdown and top bar menu"
```

---

### Task 4: Per-user installation, startup, and desktop integration

**Files:**
- Create: `data/stand-up-reminder.service`
- Create: `data/stand-up-reminder.desktop`
- Create: `data/stand-up-reminder-autostart.desktop`
- Create: `data/stand-up-reminder-symbolic.svg`
- Create: `scripts/install.sh`
- Create: `scripts/uninstall.sh`
- Create: `tests/test_install_assets.py`

**Interfaces:**
- Consumes: executable package from Tasks 1–3.
- Produces: `~/.local/bin/stand-up-reminder`, user service, Applications entry, top-bar icon, and graphical-login autostart.

- [ ] **Step 1: Write installation-asset tests**

```python
# tests/test_install_assets.py
import configparser
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallAssetTests(unittest.TestCase):
    def _desktop(self, name):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(ROOT / "data" / name, encoding="utf-8")
        return parser["Desktop Entry"]

    def test_application_launcher_starts_user_service(self):
        entry = self._desktop("stand-up-reminder.desktop")
        self.assertEqual(entry["Type"], "Application")
        self.assertEqual(entry["Exec"], "systemctl --user start stand-up-reminder.service")
        self.assertEqual(entry["Icon"], "stand-up-reminder-symbolic")

    def test_autostart_is_enabled(self):
        entry = self._desktop("stand-up-reminder-autostart.desktop")
        self.assertEqual(entry["X-GNOME-Autostart-enabled"], "true")
        self.assertEqual(entry["NoDisplay"], "true")

    def test_service_restarts_only_on_failure(self):
        service = (ROOT / "data" / "stand-up-reminder.service").read_text()
        self.assertIn("ExecStart=%h/.local/bin/stand-up-reminder", service)
        self.assertIn("Restart=on-failure", service)
        self.assertNotIn("Restart=always", service)

    def test_install_and_uninstall_scripts_are_strict(self):
        for name in ("install.sh", "uninstall.sh"):
            script = (ROOT / "scripts" / name).read_text()
            self.assertTrue(script.startswith("#!/bin/sh\nset -eu\n"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the asset tests and verify the expected failure**

Run: `python3 -m unittest tests.test_install_assets -v`

Expected: FAIL because the data files do not exist.

- [ ] **Step 3: Add systemd and desktop files**

```ini
# data/stand-up-reminder.service
[Unit]
Description=Stand Up Reminder
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=%h/.local/bin/stand-up-reminder
Restart=on-failure
RestartSec=5
```

```ini
# data/stand-up-reminder.desktop
[Desktop Entry]
Type=Application
Name=Stand Up Reminder
Comment=Take a two-minute standing break every 30 minutes
Exec=systemctl --user start stand-up-reminder.service
Icon=stand-up-reminder-symbolic
Terminal=false
Categories=Utility;GTK;
StartupNotify=false
```

```ini
# data/stand-up-reminder-autostart.desktop
[Desktop Entry]
Type=Application
Name=Stand Up Reminder
Comment=Start the standing-break reminder at login
Exec=systemctl --user start stand-up-reminder.service
Icon=stand-up-reminder-symbolic
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
OnlyShowIn=GNOME;Unity;
```

```xml
<!-- data/stand-up-reminder-symbolic.svg -->
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <g fill="#2e3436">
    <circle cx="8" cy="2.5" r="1.7"/>
    <path d="M6.4 4.6h3.2l1 4.1 2.4 2.2-.9 1-2.9-2.4-.4-1.7v6.1H7.3v-4l-1.6 1.7-2.8-.7.3-1.3 2 .4 1.7-2z"/>
  </g>
</svg>
```

- [ ] **Step 4: Add idempotent install and uninstall scripts**

```sh
#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
user_data_root=${XDG_DATA_HOME:-"$HOME/.local/share"}
user_config_root=${XDG_CONFIG_HOME:-"$HOME/.config"}
app_install_root="$user_data_root/stand-up-reminder"

install -d "$app_install_root" "$HOME/.local/bin"
install -d "$user_data_root/applications" "$user_data_root/icons/hicolor/scalable/status"
install -d "$user_config_root/autostart" "$user_config_root/systemd/user"

rm -rf "$app_install_root/stand_up_reminder"
cp -R "$project_root/stand_up_reminder" "$app_install_root/stand_up_reminder"

install -m 0755 /dev/stdin "$HOME/.local/bin/stand-up-reminder" <<'EOF'
#!/bin/sh
set -eu
user_data_root=${XDG_DATA_HOME:-"$HOME/.local/share"}
exec /usr/bin/python3 "$user_data_root/stand-up-reminder/stand_up_reminder" "$@"
EOF

install -m 0644 "$project_root/data/stand-up-reminder.desktop" \
  "$user_data_root/applications/stand-up-reminder.desktop"
install -m 0644 "$project_root/data/stand-up-reminder-autostart.desktop" \
  "$user_config_root/autostart/stand-up-reminder.desktop"
install -m 0644 "$project_root/data/stand-up-reminder.service" \
  "$user_config_root/systemd/user/stand-up-reminder.service"
install -m 0644 "$project_root/data/stand-up-reminder-symbolic.svg" \
  "$user_data_root/icons/hicolor/scalable/status/stand-up-reminder-symbolic.svg"

gtk-update-icon-cache -f -t "$user_data_root/icons/hicolor" >/dev/null 2>&1 || true
update-desktop-database "$user_data_root/applications" >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user start stand-up-reminder.service
```

```sh
#!/bin/sh
set -eu

user_data_root=${XDG_DATA_HOME:-"$HOME/.local/share"}
user_config_root=${XDG_CONFIG_HOME:-"$HOME/.config"}

systemctl --user stop stand-up-reminder.service >/dev/null 2>&1 || true
rm -f "$user_config_root/autostart/stand-up-reminder.desktop"
rm -f "$user_config_root/systemd/user/stand-up-reminder.service"
rm -f "$user_data_root/applications/stand-up-reminder.desktop"
rm -f "$user_data_root/icons/hicolor/scalable/status/stand-up-reminder-symbolic.svg"
rm -f "$HOME/.local/bin/stand-up-reminder"
rm -rf "$user_data_root/stand-up-reminder"
systemctl --user daemon-reload
```

- [ ] **Step 5: Make scripts executable and run all tests**

Run: `chmod +x scripts/install.sh scripts/uninstall.sh`

Run: `python3 -m unittest discover -s tests -v`

Expected: 19 tests pass.

- [ ] **Step 6: Commit desktop integration**

```bash
git add data scripts tests/test_install_assets.py
git commit -m "feat: add user startup and desktop integration"
```

---

### Task 5: Documentation, installation, and live verification

**Files:**
- Create: `README.md`
- Modify: installed user files below `~/.local`, `~/.config`, and the systemd user manager by running `scripts/install.sh`.

**Interfaces:**
- Consumes: all tested source and installation assets.
- Produces: a running top-bar reminder in the current GNOME session and documented controls.

- [ ] **Step 1: Write the user README**

```markdown
# Stand Up Reminder

A native Ubuntu GNOME reminder that starts a two-minute standing break after
every 30 minutes of work.

## Controls

Click the top-bar icon to see the next break, start a break immediately, choose
whether lock/suspend time counts, or quit the application. An active break is a
centered always-on-top countdown and cannot be closed through normal window
controls. Quit remains available as the deliberate way to stop the app.

## Timing modes

- **Active time only** pauses the work timer during lock and suspend.
- **Wall-clock time** counts lock and suspend; an overdue break starts after
  the session becomes available.

## Startup and relaunch

The app starts at every graphical login. Quit keeps it stopped for the current
login. Launch **Stand Up Reminder** from the Applications menu to start it
again.

## Development

Run tests with:

```bash
python3 -m unittest discover -s tests -v
```

Install or update with `scripts/install.sh`. Remove the application with
`scripts/uninstall.sh`.
```

- [ ] **Step 2: Run final automated verification**

Run: `python3 -m unittest discover -s tests -v`

Expected: 19 tests pass.

Run: `python3 -m compileall -q stand_up_reminder`

Expected: exit code 0 and no output.

- [ ] **Step 3: Install and start the application**

Run: `./scripts/install.sh`

Expected: exit code 0; `stand-up-reminder.service` becomes active.

- [ ] **Step 4: Verify installed state**

Run: `systemctl --user is-active stand-up-reminder.service`

Expected: `active`.

Run: `systemctl --user show stand-up-reminder.service -p ExecMainStatus -p NRestarts`

Expected: `ExecMainStatus=0` while active and `NRestarts=0` after a clean start.

Run: `test -x "$HOME/.local/bin/stand-up-reminder" && test -f "$HOME/.config/autostart/stand-up-reminder.desktop" && test -f "$HOME/.local/share/applications/stand-up-reminder.desktop"`

Expected: exit code 0.

- [ ] **Step 5: Exercise a short live break**

Run: `systemctl --user stop stand-up-reminder.service`

Run: `systemctl --user set-environment STAND_UP_REMINDER_WORK_SECONDS=3 STAND_UP_REMINDER_BREAK_SECONDS=5`

Run: `systemctl --user start stand-up-reminder.service`

Expected: after three seconds, a centered five-second countdown appears above other windows, ignores normal close attempts, closes at zero, and the indicator resets to another three-second work interval.

Run: `systemctl --user stop stand-up-reminder.service`

Run: `systemctl --user unset-environment STAND_UP_REMINDER_WORK_SECONDS STAND_UP_REMINDER_BREAK_SECONDS`

Run: `systemctl --user start stand-up-reminder.service`

Expected: the production service is active with a fresh 30-minute interval.

- [ ] **Step 6: Verify clean Quit and relaunch**

Action: choose **Quit** from the top-bar menu.

Run: `systemctl --user is-active stand-up-reminder.service`

Expected: `inactive`, proving `Restart=on-failure` does not override deliberate Quit.

Action: launch **Stand Up Reminder** from the GNOME Applications menu.

Run: `systemctl --user is-active stand-up-reminder.service`

Expected: `active` and exactly one top-bar indicator is visible.

- [ ] **Step 7: Commit documentation**

```bash
git add README.md
git commit -m "docs: add stand up reminder usage"
```

- [ ] **Step 8: Inspect final repository state**

Run: `git status --short --branch`

Expected: clean working tree on the current branch.
