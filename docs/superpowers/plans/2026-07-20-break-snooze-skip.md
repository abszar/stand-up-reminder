# Break Snooze and Skip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeatable five-minute break snoozing and a skip action that immediately starts a fresh 30-minute work interval.

**Architecture:** Extend the deterministic scheduler with a wall-clock `SNOOZED` phase and explicit snooze/skip operations. Keep GTK presentation and coordination thin: pure view helpers determine labels and action availability, popup callbacks call the scheduler, and the existing transition path reopens the popup.

**Tech Stack:** Python 3, `unittest`, GTK 3/PyGObject, Ayatana AppIndicator, GLib.

## Global Constraints

- Keep the fixed 30-minute work interval and two-minute break duration.
- Add a fixed five-minute snooze duration.
- Allow repeated snoozes.
- Measure snooze time using wall-clock time, including lock and suspend.
- Preserve the existing completed-break return-confirmation flow.
- Keep timing decisions in the deterministic scheduler rather than GTK.
- Do not add settings, duration controls, notifications, or persistence across application restarts.
- Target Ubuntu 24.04 with GNOME Shell 46 on X11.
- Do not require network access or new system packages.

---

### Task 1: Deterministic snooze and skip scheduler state

**Files:**
- Modify: `tests/test_scheduler.py`
- Modify: `stand_up_reminder/scheduler.py`

**Interfaces:**
- Consumes: `Scheduler.advance() -> Optional[Transition]`, `Scheduler.start_break() -> Optional[Transition]`, `Phase`, `Transition.START_BREAK`, and the existing injected clocks.
- Produces: `Phase.SNOOZED`, `Scheduler(..., snooze_seconds: float = 5 * 60)`, `Scheduler.snooze_break() -> bool`, and `Scheduler.skip_break() -> bool`.

- [ ] **Step 1: Write failing scheduler tests**

Pass a short snooze duration in `SchedulerTests.setUp`:

```python
self.scheduler = Scheduler(
    work_seconds=30,
    break_seconds=2,
    snooze_seconds=5,
    mode=TimingMode.ACTIVE,
    monotonic=self.clocks.monotonic,
    wall_clock=self.clocks.wall_clock,
)
```

Add these tests to `SchedulerTests`:

```python
def test_snooze_reopens_a_fresh_break_after_wall_clock_delay(self):
    self.scheduler.start_break()

    self.assertTrue(self.scheduler.snooze_break())
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.SNOOZED)
    self.assertEqual(snapshot.seconds_remaining, 5)
    self.assertEqual(snapshot.away_seconds, 0)

    self.clocks.advance(4, suspended=True)
    self.assertIsNone(self.scheduler.advance())
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 1)

    self.clocks.advance(1, suspended=True)
    self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.BREAK)
    self.assertEqual(snapshot.seconds_remaining, 2)
    self.assertEqual(snapshot.away_seconds, 0)

def test_break_can_be_snoozed_repeatedly(self):
    self.scheduler.start_break()
    self.assertTrue(self.scheduler.snooze_break())
    self.clocks.advance(5)
    self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)

    self.assertTrue(self.scheduler.snooze_break())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.SNOOZED)
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 5)

def test_overdue_snooze_starts_break_on_unlock(self):
    self.scheduler.start_break()
    self.scheduler.snooze_break()
    self.scheduler.set_locked(True)

    self.clocks.advance(7, suspended=True)
    self.assertEqual(
        self.scheduler.set_locked(False), Transition.START_BREAK
    )
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.BREAK)
    self.assertEqual(snapshot.seconds_remaining, 2)
    self.assertFalse(snapshot.locked)

def test_skip_break_starts_full_work_interval_at_click_time(self):
    self.scheduler.start_break()
    self.clocks.advance(1)

    self.assertTrue(self.scheduler.skip_break())
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.WORK)
    self.assertEqual(snapshot.seconds_remaining, 30)
    self.assertEqual(snapshot.away_seconds, 0)

    self.clocks.advance(6)
    self.scheduler.advance()
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 24)

def test_snooze_and_skip_are_rejected_outside_active_break(self):
    self.assertFalse(self.scheduler.snooze_break())
    self.assertFalse(self.scheduler.skip_break())

    self.scheduler.start_break()
    self.assertTrue(self.scheduler.snooze_break())
    self.assertFalse(self.scheduler.snooze_break())
    self.assertFalse(self.scheduler.skip_break())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.SNOOZED)

def test_snooze_at_break_deadline_cannot_bypass_return(self):
    self.scheduler.start_break()
    self.clocks.advance(2)

    self.assertFalse(self.scheduler.snooze_break())
    self.assertEqual(
        self.scheduler.snapshot().phase, Phase.AWAITING_RETURN
    )

def test_skip_at_break_deadline_cannot_bypass_return(self):
    self.scheduler.start_break()
    self.clocks.advance(2)

    self.assertFalse(self.scheduler.skip_break())
    self.assertEqual(
        self.scheduler.snapshot().phase, Phase.AWAITING_RETURN
    )

def test_work_reset_cannot_bypass_snoozed_break(self):
    self.scheduler.start_break()
    self.scheduler.snooze_break()

    self.assertFalse(self.scheduler.reset_work_interval())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.SNOOZED)
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 5)
```

- [ ] **Step 2: Run the focused scheduler tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_scheduler.SchedulerTests -v
```

Expected: FAIL in `setUp` because `Scheduler.__init__()` does not yet accept `snooze_seconds`.

- [ ] **Step 3: Implement the snoozed phase and explicit actions**

In `stand_up_reminder/scheduler.py`, add the phase:

```python
class Phase(str, Enum):
    WORK = "work"
    SNOOZED = "snoozed"
    BREAK = "break"
    AWAITING_RETURN = "awaiting_return"
```

Add the constructor parameter and assignment:

```python
def __init__(
    self,
    *,
    work_seconds: float = 30 * 60,
    break_seconds: float = 2 * 60,
    snooze_seconds: float = 5 * 60,
    mode: TimingMode = TimingMode.ACTIVE,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
) -> None:
    self.work_seconds = float(work_seconds)
    self.break_seconds = float(break_seconds)
    self.snooze_seconds = float(snooze_seconds)
```

In `advance()`, place the snooze branch after the existing break/awaiting-return branch and before the lock/work branch so snooze always uses wall time:

```python
if self.phase is Phase.SNOOZED:
    self.remaining = max(0.0, self.remaining - wall_delta)
    if self.remaining > 0:
        return None
    self.phase = Phase.BREAK
    self.remaining = self.break_seconds
    self.away_elapsed = 0.0
    return Transition.START_BREAK
```

Add the two public operations:

```python
def snooze_break(self) -> bool:
    self.advance()
    if self.phase is not Phase.BREAK:
        return False
    self.phase = Phase.SNOOZED
    self.remaining = self.snooze_seconds
    self.away_elapsed = 0.0
    return True

def skip_break(self) -> bool:
    self.advance()
    if self.phase is not Phase.BREAK:
        return False
    self.phase = Phase.WORK
    self.remaining = self.work_seconds
    self.away_elapsed = 0.0
    return True
```

Prevent manual break starts and the indicator reset action from bypassing snooze:

```python
def start_break(self) -> Optional[Transition]:
    transition = self.advance()
    if self.phase in (
        Phase.SNOOZED,
        Phase.BREAK,
        Phase.AWAITING_RETURN,
    ):
        return transition
    self.phase = Phase.BREAK
    self.remaining = self.break_seconds
    self.away_elapsed = 0.0
    return Transition.START_BREAK

def reset_work_interval(self) -> bool:
    self.advance()
    if self.phase in (Phase.SNOOZED, Phase.BREAK):
        return False
    if self.phase is Phase.AWAITING_RETURN:
        return self.confirm_return() is Transition.END_BREAK
    self.remaining = self.work_seconds
    return True
```

- [ ] **Step 4: Run all scheduler tests**

Run:

```bash
python3 -m unittest tests.test_scheduler.SchedulerTests -v
```

Expected: all scheduler tests pass, including existing work, lock, suspend, break-completion, and return-confirmation tests.

- [ ] **Step 5: Commit the scheduler state model**

```bash
git add stand_up_reminder/scheduler.py tests/test_scheduler.py
git commit -m "feat: add break snooze and skip scheduling"
```

---

### Task 2: Pure popup and indicator view models

**Files:**
- Modify: `tests/test_application_helpers.py`
- Modify: `stand_up_reminder/application.py`

**Interfaces:**
- Consumes: `Phase.SNOOZED` from Task 1 and the existing `format_duration(seconds: int) -> str`.
- Produces: `BreakView.can_snooze: bool`, `BreakView.can_skip: bool`, `IndicatorView`, and `indicator_view(phase: Phase, seconds_remaining: int, away_seconds: int) -> IndicatorView`.

- [ ] **Step 1: Write failing presentation-helper tests**

Extend the existing `BreakViewTests`:

```python
def test_minimum_break_view(self):
    view = application.break_view(Phase.BREAK, 75, 45)
    self.assertEqual(view.title, "Time to stand up")
    self.assertEqual(view.countdown, "01:15")
    self.assertEqual(view.away, "Away for 00:45")
    self.assertTrue(view.can_snooze)
    self.assertTrue(view.can_skip)
    self.assertFalse(view.can_return)

def test_awaiting_return_view(self):
    view = application.break_view(Phase.AWAITING_RETURN, 0, 15 * 60)
    self.assertEqual(view.title, "Break complete")
    self.assertEqual(view.countdown, "00:00")
    self.assertEqual(view.away, "Away for 15:00")
    self.assertFalse(view.can_snooze)
    self.assertFalse(view.can_skip)
    self.assertTrue(view.can_return)

def test_snoozed_view_has_no_popup_actions(self):
    view = application.break_view(Phase.SNOOZED, 5 * 60, 0)
    self.assertFalse(view.can_snooze)
    self.assertFalse(view.can_skip)
    self.assertFalse(view.can_return)
```

Add the indicator cases:

```python
class IndicatorViewTests(unittest.TestCase):
    def test_work_view(self):
        view = application.indicator_view(Phase.WORK, 24 * 60, 0)
        self.assertEqual(view.status, "Next break in 24:00")
        self.assertTrue(view.can_start_break)
        self.assertTrue(view.can_reset_work)

    def test_snoozed_view(self):
        view = application.indicator_view(Phase.SNOOZED, 4 * 60 + 9, 0)
        self.assertEqual(view.status, "Break snoozed for 04:09")
        self.assertFalse(view.can_start_break)
        self.assertFalse(view.can_reset_work)

    def test_active_break_view(self):
        view = application.indicator_view(Phase.BREAK, 75, 45)
        self.assertEqual(view.status, "Break in progress")
        self.assertFalse(view.can_start_break)
        self.assertFalse(view.can_reset_work)

    def test_awaiting_return_view(self):
        view = application.indicator_view(
            Phase.AWAITING_RETURN, 0, 15 * 60
        )
        self.assertEqual(view.status, "Away for 15:00")
        self.assertFalse(view.can_start_break)
        self.assertTrue(view.can_reset_work)
```

- [ ] **Step 2: Run presentation-helper tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_application_helpers -v
```

Expected: FAIL because `BreakView` has no `can_snooze` or `can_skip` fields and `indicator_view` does not exist.

- [ ] **Step 3: Implement the pure view models**

Replace `BreakView` and `break_view` in `stand_up_reminder/application.py` with:

```python
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
```

Add the indicator view model below it:

```python
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
```

- [ ] **Step 4: Run presentation-helper tests**

Run:

```bash
python3 -m unittest tests.test_application_helpers -v
```

Expected: all application helper tests pass.

- [ ] **Step 5: Commit the view models**

```bash
git add stand_up_reminder/application.py tests/test_application_helpers.py
git commit -m "feat: describe snooze and skip interface states"
```

---

### Task 3: GTK controls, coordinator wiring, and user documentation

**Files:**
- Modify: `tests/test_application_helpers.py`
- Modify: `stand_up_reminder/application.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Scheduler.snooze_break() -> bool`, `Scheduler.skip_break() -> bool`, `BreakView.can_snooze`, `BreakView.can_skip`, and `indicator_view(...) -> IndicatorView` from Tasks 1 and 2.
- Produces: `ReminderApplication._snooze_break(button) -> None`, `ReminderApplication._skip_break(button) -> None`, and popup buttons labeled `Give me 5 minutes` and `Skip this break`.

- [ ] **Step 1: Write failing coordinator callback tests**

Add these imports to `tests/test_application_helpers.py`:

```python
from types import SimpleNamespace
from unittest.mock import Mock
```

Add these tests:

```python
class BreakActionCoordinatorTests(unittest.TestCase):
    def make_coordinator(self):
        return SimpleNamespace(
            scheduler=Mock(),
            window=Mock(),
            _update_interface=Mock(),
        )

    def test_successful_snooze_hides_popup_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.snooze_break.return_value = True

        application.ReminderApplication._snooze_break(coordinator, None)

        coordinator.window.hide.assert_called_once_with()
        coordinator._update_interface.assert_called_once_with()

    def test_rejected_snooze_keeps_popup_visible_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.snooze_break.return_value = False

        application.ReminderApplication._snooze_break(coordinator, None)

        coordinator.window.hide.assert_not_called()
        coordinator._update_interface.assert_called_once_with()

    def test_successful_skip_hides_popup_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.skip_break.return_value = True

        application.ReminderApplication._skip_break(coordinator, None)

        coordinator.window.hide.assert_called_once_with()
        coordinator._update_interface.assert_called_once_with()

    def test_rejected_skip_keeps_popup_visible_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.skip_break.return_value = False

        application.ReminderApplication._skip_break(coordinator, None)

        coordinator.window.hide.assert_not_called()
        coordinator._update_interface.assert_called_once_with()
```

- [ ] **Step 2: Run the coordinator tests and verify failure**

Run:

```bash
python3 -m unittest \
  tests.test_application_helpers.BreakActionCoordinatorTests -v
```

Expected: FAIL with `AttributeError` because `_snooze_break` and `_skip_break` do not exist.

- [ ] **Step 3: Add the five-minute production duration**

Add the constant in `stand_up_reminder/application.py`:

```python
DEFAULT_SNOOZE_SECONDS = 5 * 60
```

In `_initialize()`, load and validate it with the existing development duration overrides, then pass it to `Scheduler`:

```python
snooze_seconds = float(
    os.environ.get(
        "STAND_UP_REMINDER_SNOOZE_SECONDS", DEFAULT_SNOOZE_SECONDS
    )
)
if work_seconds <= 0 or break_seconds <= 0 or snooze_seconds <= 0:
    raise ValueError("timer durations must be positive")

self.scheduler = Scheduler(
    work_seconds=work_seconds,
    break_seconds=break_seconds,
    snooze_seconds=snooze_seconds,
    mode=settings.mode,
)
```

- [ ] **Step 4: Add and style the popup actions**

Change the `BreakWindow` constructor signature:

```python
def __init__(
    self,
    application: Gtk.Application,
    break_seconds: int,
    on_snooze,
    on_skip,
    on_return,
) -> None:
```

Create the action row before the return button:

```python
self.break_actions = Gtk.Box(
    orientation=Gtk.Orientation.HORIZONTAL, spacing=8
)

self.snooze_button = Gtk.Button(label="Give me 5 minutes")
self.snooze_button.set_hexpand(True)
self.snooze_button.set_no_show_all(True)
self.snooze_button.get_style_context().add_class("break-snooze")
self.snooze_button.connect("clicked", on_snooze)

self.skip_button = Gtk.Button(label="Skip this break")
self.skip_button.set_hexpand(True)
self.skip_button.set_no_show_all(True)
self.skip_button.get_style_context().add_class("break-skip")
self.skip_button.connect("clicked", on_skip)

self.break_actions.pack_start(self.snooze_button, True, True, 0)
self.break_actions.pack_start(self.skip_button, True, True, 0)
```

Pack the row immediately before `self.return_button`:

```python
card.pack_start(self.break_actions, False, False, 0)
card.pack_start(self.return_button, False, False, 0)
```

Extend the existing CSS so snooze shares the high-contrast primary style and skip uses a quieter secondary style:

```css
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
```

At the end of `BreakWindow.update_state()`, apply the pure view state:

```python
self.snooze_button.set_visible(view.can_snooze)
self.skip_button.set_visible(view.can_skip)
self.return_button.set_visible(view.can_return)
```

- [ ] **Step 5: Wire the window callbacks and indicator state**

Construct the window with all three callbacks:

```python
self.window = BreakWindow(
    self,
    int(break_seconds),
    self._snooze_break,
    self._skip_break,
    self._confirm_return,
)
```

Add the coordinator callbacks:

```python
def _snooze_break(self, _button) -> None:
    if self.scheduler.snooze_break():
        self.window.hide()
    self._update_interface()

def _skip_break(self, _button) -> None:
    if self.scheduler.skip_break():
        self.window.hide()
    self._update_interface()
```

Replace the phase-specific indicator label/sensitivity block at the start of `_update_interface()` with:

```python
view = indicator_view(
    snapshot.phase,
    snapshot.seconds_remaining,
    snapshot.away_seconds,
)
self.status_item.set_label(view.status)
self.start_item.set_sensitive(view.can_start_break)
self.reset_item.set_sensitive(view.can_reset_work)
```

Keep the existing window-update condition limited to `BREAK` and `AWAITING_RETURN`; a snoozed popup must stay hidden.

- [ ] **Step 6: Run the focused helper and coordinator tests**

Run:

```bash
python3 -m unittest tests.test_application_helpers -v
```

Expected: all format, progress, popup view, indicator view, and coordinator callback tests pass.

- [ ] **Step 7: Update user-facing controls documentation**

Replace the opening paragraph under `## Controls` in `README.md` with:

```markdown
Click the top-bar icon to see the next break, start a break immediately, mark
your return from a longer break, choose whether lock/suspend time counts, or
quit the application. During the two-minute countdown, **Give me 5 minutes**
closes the popup and brings it back five wall-clock minutes later with a fresh
two-minute countdown. Snoozing can be repeated. **Skip this break** closes the
popup and immediately starts a fresh 30-minute work interval.

When a break is allowed to finish, the centered always-on-top popup changes to
**Break complete** and reveals **I'm back — start 30-minute timer**. Click that
button when you return to close the popup and begin a fresh work interval.
```

- [ ] **Step 8: Run the complete automated verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q stand_up_reminder tests
git diff --check
```

Expected: all unit tests pass, compilation exits zero without output, and `git diff --check` exits zero without output.

- [ ] **Step 9: Perform a short-duration graphical smoke check when a display is available**

Run:

```bash
env \
  STAND_UP_REMINDER_WORK_SECONDS=2 \
  STAND_UP_REMINDER_BREAK_SECONDS=4 \
  STAND_UP_REMINDER_SNOOZE_SECONDS=5 \
  python3 -m stand_up_reminder
```

Verify:

1. The first popup shows **Give me 5 minutes** and **Skip this break**.
2. Snooze hides it for five seconds and returns with a fresh `00:04` countdown.
3. Snooze can be selected again.
4. Skip closes the popup and the indicator starts a fresh work countdown.
5. Letting the countdown reach zero hides both new actions and shows the existing return button.
6. Quit from the indicator after the check.

If no graphical display is available, record that the smoke check was skipped and rely on the automated verification.

- [ ] **Step 10: Commit the GTK integration and documentation**

```bash
git add README.md stand_up_reminder/application.py \
  tests/test_application_helpers.py
git commit -m "feat: add break snooze and skip controls"
```
