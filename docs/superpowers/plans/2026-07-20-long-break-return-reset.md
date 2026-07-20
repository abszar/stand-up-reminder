# Long-Break Return Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a top-bar “I'm back — restart 30-minute timer” action that resets a partially elapsed work interval after a longer break.

**Architecture:** Add one deterministic scheduler command that succeeds only during the work phase. Wire it to a GTK menu item directly below Start break now, keep it disabled during enforced breaks, and reuse the existing interface refresh path so the status immediately shows 30:00.

**Tech Stack:** Python 3.12, unittest, GTK 3, AyatanaAppIndicator3, existing per-user installer and systemd service.

## Global Constraints

- Preserve fixed 30-minute work and 2-minute break durations.
- The new reset action must not dismiss or shorten an active enforced break.
- No automatic idle detection.
- Do not add dependencies.
- Never use the prohibited vendor name in commit messages.

---

### Task 1: Scheduler reset command and top-bar action

**Files:**
- Modify: `stand_up_reminder/scheduler.py`
- Modify: `stand_up_reminder/application.py`
- Modify: `tests/test_scheduler.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing `Scheduler.advance()`, `Phase`, and GTK menu refresh behavior.
- Produces: `Scheduler.reset_work_interval() -> bool` and `ReminderApplication._reset_work_interval(item) -> None`.

- [ ] **Step 1: Write failing scheduler tests**

Add these tests to `SchedulerTests`:

```python
def test_long_break_return_resets_partial_work_interval(self):
    self.clocks.advance(11)
    self.assertTrue(self.scheduler.reset_work_interval())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

def test_repeated_long_break_return_resets_are_full_intervals(self):
    self.clocks.advance(8)
    self.scheduler.reset_work_interval()
    self.clocks.advance(6)
    self.assertTrue(self.scheduler.reset_work_interval())
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

def test_long_break_return_cannot_dismiss_active_break(self):
    self.scheduler.start_break()
    self.assertFalse(self.scheduler.reset_work_interval())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)
    self.assertEqual(self.scheduler.snapshot().seconds_remaining, 2)

def test_long_break_return_at_deadline_preserves_enforced_break(self):
    self.clocks.advance(30)
    self.assertFalse(self.scheduler.reset_work_interval())
    self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)
```

- [ ] **Step 2: Run the new tests and verify the expected failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_scheduler.SchedulerTests.test_long_break_return_resets_partial_work_interval \
  tests.test_scheduler.SchedulerTests.test_repeated_long_break_return_resets_are_full_intervals \
  tests.test_scheduler.SchedulerTests.test_long_break_return_cannot_dismiss_active_break \
  tests.test_scheduler.SchedulerTests.test_long_break_return_at_deadline_preserves_enforced_break -v
```

Expected: four errors reporting that `Scheduler` has no `reset_work_interval` method.

- [ ] **Step 3: Implement the scheduler command**

Add to `Scheduler` immediately after `start_break`:

```python
def reset_work_interval(self) -> bool:
    self.advance()
    if self.phase is Phase.BREAK:
        return False
    self.remaining = self.work_seconds
    return True
```

The initial `advance()` both accounts for elapsed time and prevents a reset click at the exact deadline from bypassing the enforced break.

- [ ] **Step 4: Run scheduler tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_scheduler -v`

Expected: all scheduler tests pass, including the four new reset cases.

- [ ] **Step 5: Add the GTK menu item and handler**

In `ReminderApplication.__init__`, initialize:

```python
self.reset_item = None
```

In `_build_indicator`, place this directly after the Start break now item and before the first separator:

```python
self.reset_item = Gtk.MenuItem(
    label="I'm back — restart 30-minute timer"
)
self.reset_item.connect("activate", self._reset_work_interval)
menu.append(self.reset_item)
```

In `_update_interface`, disable it during breaks and enable it during work:

```python
if snapshot.phase is Phase.BREAK:
    self.reset_item.set_sensitive(False)
else:
    self.reset_item.set_sensitive(True)
```

Add the handler beside `_start_break_now`:

```python
def _reset_work_interval(self, _item) -> None:
    if self.scheduler.reset_work_interval():
        self._update_interface()
```

- [ ] **Step 6: Update the user guide**

Change the Controls paragraph in `README.md` to name the new action and explain that it starts a fresh 30-minute timer after returning from a longer break. State that it is unavailable during the enforced countdown.

- [ ] **Step 7: Run complete verification**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`

Expected: 29 tests pass.

Run: `python3 -m compileall -q stand_up_reminder`

Expected: exit code 0.

Run: `git diff --check`

Expected: exit code 0 with no output.

- [ ] **Step 8: Commit the feature**

```bash
git add stand_up_reminder/scheduler.py stand_up_reminder/application.py tests/test_scheduler.py README.md
git commit -m "feat: add long break return reset"
```

- [ ] **Step 9: Install and verify the live top-bar action**

Run: `./scripts/install.sh`

Expected: the user service restarts active with the final source.

Read the exported AppIndicator menu with `com.canonical.dbusmenu.GetLayout`. Verify “I'm back — restart 30-minute timer” appears directly below “Start break now.”

Invoke the new item after allowing a shortened test work interval to elapse. Verify the live status becomes `Next break in 30:00` and the item is disabled while a shortened enforced countdown is active. Remove all temporary duration variables and restart the production service.

Run:

```bash
systemctl --user is-active stand-up-reminder.service
git status --short --branch
```

Expected: service is `active`; repository is clean on `master`.
