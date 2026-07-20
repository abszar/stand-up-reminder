# Persistent Break Return Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every break popup open after the two-minute minimum, show total wall-clock absence, and begin the next 30-minute work interval only when the user explicitly confirms their return.

**Architecture:** Extend the deterministic scheduler with an `AWAITING_RETURN` phase and wall-clock absence tracking. Keep the GTK window presentation-only: it receives a scheduler snapshot, renders the countdown/count-up and return button, then invokes one coordinator callback to confirm return.

**Tech Stack:** Python 3, `unittest`, GTK 3/PyGObject, Ayatana AppIndicator, GLib, systemd user service.

## Global Constraints

- Target Ubuntu 24.04 with GNOME Shell 46 on X11.
- Use the already-installed Python 3, GTK 3, PyGObject, Ayatana AppIndicator, and Ubuntu AppIndicators GNOME extension.
- Do not require network access or new system packages.
- Install entirely for the current user; administrator access is unnecessary.
- Use fixed intervals: 30 minutes between breaks and 2 minutes per break.
- Break countdown and absence timing always use wall-clock time, independent of the work timing policy.
- Before the enforced minimum ends, no normal control may dismiss the popup.
- Application Quit remains an intentional escape hatch.

---

### Task 1: Scheduler awaiting-return state

**Files:**
- Modify: `tests/test_scheduler.py`
- Modify: `stand_up_reminder/scheduler.py`

**Interfaces:**
- Consumes: existing `Scheduler`, `Phase`, `Transition`, `Snapshot`, `FakeClocks`.
- Produces: `Phase.AWAITING_RETURN`, `Transition.BREAK_COMPLETE`, `Scheduler.confirm_return() -> Optional[Transition]`, and `Snapshot.away_seconds: int`.

- [ ] **Step 1: Replace the automatic-reset test and add wall-clock absence tests**

Add these tests to `SchedulerTests`, replacing `test_break_completion_resets_full_work_interval` and `test_break_pauses_while_locked_for_both_modes`:

```python
def test_break_completion_waits_for_explicit_return(self):
    self.scheduler.start_break()
    self.clocks.advance(2)
    self.assertEqual(self.scheduler.advance(), Transition.BREAK_COMPLETE)
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.AWAITING_RETURN)
    self.assertEqual(snapshot.seconds_remaining, 0)
    self.assertEqual(snapshot.away_seconds, 2)

def test_away_time_counts_from_break_start(self):
    self.scheduler.start_break()
    self.clocks.advance(1)
    self.scheduler.advance()
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.BREAK)
    self.assertEqual(snapshot.seconds_remaining, 1)
    self.assertEqual(snapshot.away_seconds, 1)

def test_break_and_away_time_count_lock_and_suspend(self):
    self.scheduler.start_break()
    self.scheduler.set_locked(True)
    self.clocks.advance(5, suspended=True)
    self.assertEqual(self.scheduler.advance(), Transition.BREAK_COMPLETE)
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.AWAITING_RETURN)
    self.assertEqual(snapshot.away_seconds, 5)
    self.assertIsNone(self.scheduler.set_locked(False))

def test_away_time_continues_while_awaiting_return(self):
    self.scheduler.start_break()
    self.clocks.advance(2)
    self.scheduler.advance()
    self.clocks.advance(13, suspended=True)
    self.scheduler.advance()
    self.assertEqual(self.scheduler.snapshot().away_seconds, 15)
```

- [ ] **Step 2: Run the focused scheduler tests and verify they fail**

Run: `python3 -m unittest tests.test_scheduler.SchedulerTests -v`

Expected: failures because `AWAITING_RETURN`, `BREAK_COMPLETE`, and `away_seconds` do not exist and break timing currently pauses while locked.

- [ ] **Step 3: Add explicit return-confirmation tests**

Add:

```python
def test_return_confirmation_is_rejected_during_minimum(self):
    self.scheduler.start_break()
    self.clocks.advance(1)
    self.assertIsNone(self.scheduler.confirm_return())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)

def test_return_confirmation_starts_full_interval_at_click_time(self):
    self.scheduler.start_break()
    self.clocks.advance(7)
    self.scheduler.advance()
    self.assertEqual(self.scheduler.confirm_return(), Transition.END_BREAK)
    snapshot = self.scheduler.snapshot()
    self.assertEqual(snapshot.phase, Phase.WORK)
    self.assertEqual(snapshot.seconds_remaining, 30)
    self.assertEqual(snapshot.away_seconds, 0)
    self.clocks.advance(6)
    self.scheduler.advance()
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 24)

def test_work_reset_confirms_return_after_minimum(self):
    self.scheduler.start_break()
    self.clocks.advance(2)
    self.scheduler.advance()
    self.assertTrue(self.scheduler.reset_work_interval())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

def test_manual_start_is_ignored_while_awaiting_return(self):
    self.scheduler.start_break()
    self.clocks.advance(2)
    self.scheduler.advance()
    self.assertIsNone(self.scheduler.start_break())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.AWAITING_RETURN)
```

Keep the existing partially elapsed work reset tests. Update `test_long_break_return_cannot_dismiss_active_break` to advance one second before asserting rejection so it exercises the enforced minimum.

- [ ] **Step 4: Implement the scheduler state and wall-clock break accounting**

In `scheduler.py`:

```python
class Phase(str, Enum):
    WORK = "work"
    BREAK = "break"
    AWAITING_RETURN = "awaiting_return"


class Transition(str, Enum):
    START_BREAK = "start_break"
    BREAK_COMPLETE = "break_complete"
    END_BREAK = "end_break"


@dataclass(frozen=True)
class Snapshot:
    phase: Phase
    seconds_remaining: int
    away_seconds: int
    locked: bool
    mode: TimingMode
```

Initialize `self.away_elapsed = 0.0`. In `advance()`, always add `wall_delta` to `away_elapsed` during `BREAK` and `AWAITING_RETURN`, even when locked. Subtract `wall_delta` from `remaining` during `BREAK`; when it reaches zero set `phase = Phase.AWAITING_RETURN`, leave `remaining = 0.0`, and emit `Transition.BREAK_COMPLETE`. `AWAITING_RETURN` must never transition automatically.

Use these exact return paths:

```python
def confirm_return(self) -> Optional[Transition]:
    transition = self.advance()
    if self.phase is not Phase.AWAITING_RETURN:
        return transition
    self.phase = Phase.WORK
    self.remaining = self.work_seconds
    self.away_elapsed = 0.0
    return Transition.END_BREAK

def reset_work_interval(self) -> bool:
    self.advance()
    if self.phase is Phase.BREAK:
        return False
    if self.phase is Phase.AWAITING_RETURN:
        return self.confirm_return() is Transition.END_BREAK
    self.remaining = self.work_seconds
    return True
```

When entering `BREAK`, set `away_elapsed = 0.0`. In `snapshot()`, expose `away_seconds=int(math.floor(max(0.0, self.away_elapsed)))`.

Update manual start so neither active break phase can be restarted:

```python
def start_break(self) -> Optional[Transition]:
    transition = self.advance()
    if self.phase in (Phase.BREAK, Phase.AWAITING_RETURN):
        return transition
    self.phase = Phase.BREAK
    self.remaining = self.break_seconds
    self.away_elapsed = 0.0
    return Transition.START_BREAK
```

- [ ] **Step 5: Run scheduler tests and verify they pass**

Run: `python3 -m unittest tests.test_scheduler.SchedulerTests -v`

Expected: all scheduler tests pass, including lock/suspend wall-clock absence and the existing work timing-policy tests.

- [ ] **Step 6: Commit the scheduler state model**

```bash
git add stand_up_reminder/scheduler.py tests/test_scheduler.py
git commit -m "feat: require return after standing break"
```

### Task 2: Persistent popup and indicator integration

**Files:**
- Modify: `tests/test_application_helpers.py`
- Modify: `stand_up_reminder/application.py`

**Interfaces:**
- Consumes: `Snapshot.phase`, `Snapshot.seconds_remaining`, `Snapshot.away_seconds`, `Transition.BREAK_COMPLETE`, `Transition.END_BREAK`, and `Scheduler.confirm_return()` from Task 1.
- Produces: `BreakWindow.update_state(phase: Phase, seconds_remaining: int, away_seconds: int) -> None` and popup return callback wiring.

- [ ] **Step 1: Add presentation helper tests**

Import `Phase` and the new helper `break_view` in `tests/test_application_helpers.py`, then add:

```python
class BreakViewTests(unittest.TestCase):
    def test_minimum_break_view(self):
        view = break_view(Phase.BREAK, 75, 45)
        self.assertEqual(view.title, "Time to stand up")
        self.assertEqual(view.countdown, "01:15")
        self.assertEqual(view.away, "Away for 00:45")
        self.assertFalse(view.can_return)

    def test_awaiting_return_view(self):
        view = break_view(Phase.AWAITING_RETURN, 0, 15 * 60)
        self.assertEqual(view.title, "Break complete")
        self.assertEqual(view.countdown, "00:00")
        self.assertEqual(view.away, "Away for 15:00")
        self.assertTrue(view.can_return)
```

- [ ] **Step 2: Run helper tests and verify they fail**

Run: `python3 -m unittest tests.test_application_helpers.BreakViewTests -v`

Expected: import failure because `break_view` and `BreakView` do not exist.

- [ ] **Step 3: Implement the pure view model**

Add `dataclass` import and:

```python
@dataclass(frozen=True)
class BreakView:
    title: str
    countdown: str
    away: str
    can_return: bool


def break_view(phase: Phase, seconds_remaining: int, away_seconds: int) -> BreakView:
    awaiting = phase is Phase.AWAITING_RETURN
    return BreakView(
        title="Break complete" if awaiting else "Time to stand up",
        countdown=format_duration(seconds_remaining),
        away=f"Away for {format_duration(away_seconds)}",
        can_return=awaiting,
    )
```

- [ ] **Step 4: Extend the break card and render both break phases**

Change `BreakWindow.__init__` to accept `on_return`, use a compact `440 x 350` default size, and keep it centered, undecorated, non-resizable, and always on top. Store the eyebrow as `self.eyebrow`; add:

```python
self.away = Gtk.Label(label="Away for 00:00")
self.away.set_xalign(0.0)
self.away.get_style_context().add_class("break-away")

self.return_button = Gtk.Button(label="I'm back — start 30-minute timer")
self.return_button.set_no_show_all(True)
self.return_button.connect("clicked", on_return)
```

Pack `self.away` below the countdown and the button below the prompt. Add this CSS:

```css
.break-away {
    color: #c9ddd5;
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 16px;
    font-weight: 600;
}
.break-return {
    min-height: 38px;
    border-radius: 6px;
    color: #18312e;
    background-color: #f2a65a;
    font-family: Cantarell, sans-serif;
    font-size: 15px;
    font-weight: 700;
}
```

Assign the button's style class with
`self.return_button.get_style_context().add_class("break-return")`.

Replace `set_seconds()` with:

```python
def update_state(self, phase: Phase, seconds_remaining: int, away_seconds: int) -> None:
    view = break_view(phase, seconds_remaining, away_seconds)
    self.set_title(view.title)
    self.eyebrow.set_text(view.title.upper())
    self.countdown.set_text(view.countdown)
    self.away.set_text(view.away)
    self.progress.set_fraction(
        break_progress_fraction(seconds_remaining, self.break_seconds)
    )
    self.return_button.set_visible(view.can_return)
```

Construct it as `BreakWindow(self, int(break_seconds), self._confirm_return)`.

- [ ] **Step 5: Wire transitions, lock restoration, and indicator state**

Treat both `Phase.BREAK` and `Phase.AWAITING_RETURN` as active popup phases in `do_activate()` and `_set_locked()`. `Transition.BREAK_COMPLETE` must not hide the window. Add:

```python
def _confirm_return(self, _button) -> None:
    self._apply_transition(self.scheduler.confirm_return())
    self._update_interface()
```

In `_show_break()` and `_update_interface()`, call `window.update_state(...)`. For `AWAITING_RETURN`, set status to `Away for MM:SS`, disable Start break now, and enable the top-bar return item. For `BREAK`, retain `Break in progress` and disable both actions. For `WORK`, retain the existing countdown and enable both actions.

Update `_reset_work_interval()` so an awaiting-return reset hides the popup:

```python
def _reset_work_interval(self, _item) -> None:
    was_awaiting = self.scheduler.snapshot().phase is Phase.AWAITING_RETURN
    if self.scheduler.reset_work_interval():
        if was_awaiting and self.window:
            self.window.hide()
        self._update_interface()
```

- [ ] **Step 6: Run helper and full automated tests**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass with no failures or errors.

- [ ] **Step 7: Commit the GTK integration**

```bash
git add stand_up_reminder/application.py tests/test_application_helpers.py
git commit -m "feat: keep break open until return"
```

### Task 3: Documentation, installation, and live verification

**Files:**
- Modify: `README.md`
- Verify: `scripts/install.sh`
- Verify installed user files under `~/.local/share/stand-up-reminder`, `~/.config/autostart`, and `~/.config/systemd/user`.

**Interfaces:**
- Consumes: completed scheduler and GTK behavior from Tasks 1–2.
- Produces: updated user documentation and a running installed application at production timings.

- [ ] **Step 1: Document the return flow**

Update Controls to state that the popup shows `Away for MM:SS`, remains open after the two-minute minimum, and reveals **I'm back — start 30-minute timer**. Explain that either this button or the enabled top-bar return action closes the break and starts the next full work interval.

- [ ] **Step 2: Run static and automated verification**

Run:

```bash
python3 -m compileall -q stand_up_reminder
python3 -m unittest discover -s tests -v
git diff --check
```

Expected: compilation succeeds, every test passes, and `git diff --check` prints nothing.

- [ ] **Step 3: Install the updated application**

Run: `./scripts/install.sh`

Expected: installer updates the current-user application files, refreshes the user service, and starts `stand-up-reminder.service` without administrator privileges.

- [ ] **Step 4: Verify installed and live state**

Run:

```bash
systemctl --user is-active stand-up-reminder.service
systemctl --user status stand-up-reminder.service --no-pager
cmp stand_up_reminder/scheduler.py "$HOME/.local/share/stand-up-reminder/stand_up_reminder/scheduler.py"
cmp stand_up_reminder/application.py "$HOME/.local/share/stand-up-reminder/stand_up_reminder/application.py"
```

Expected: service is `active (running)` and both `cmp` commands produce no output.

Restart temporarily with `STAND_UP_REMINDER_WORK_SECONDS=3` and `STAND_UP_REMINDER_BREAK_SECONDS=2`; observe that the popup opens, remains after `00:00`, shows increasing away time, reveals the return button only after two seconds, and closes when return is confirmed. Verify the indicator resets to a fresh short work interval. Remove the temporary environment overrides and restart the production service.

- [ ] **Step 5: Confirm production timing and clean journal**

Run:

```bash
systemctl --user show stand-up-reminder.service -p Environment --value
journalctl --user -u stand-up-reminder.service -n 40 --no-pager
```

Expected: no short-duration environment overrides remain, the process is running with 30-minute/2-minute defaults, and there are no new startup tracebacks or GTK errors.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md
git commit -m "docs: explain persistent break return"
```
