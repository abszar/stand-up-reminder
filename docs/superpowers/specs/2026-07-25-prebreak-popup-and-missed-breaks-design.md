# Pre-break countdown popup and missed-break tracking

Date: 2026-07-25. Approved by Abdelali.

## Problem

The pre-break desktop notification is easy to miss, and a break that
completes while the user is at another computer can only be confirmed with
"I'm back", which wrongly counts it as taken.

## Design

### Pre-break popup replaces the notification

- The `Gio.Notification` warning is removed, along with its withdraw call.
- On `WARN_BREAK`, the break window itself appears (no monitor dimming)
  showing "Break coming up", a live countdown of the seconds until the
  break, the line "Time to stand up in MM:SS", and the draining progress
  bar. It has no buttons and cannot be closed.
- `break_view` renders this state when given `Phase.WORK`; the window uses
  `warning_seconds` as the progress denominator in that state.
- When the countdown reaches zero the window becomes the normal break
  screen in place; dimmers and the optional sound start then.
- `warning_seconds` keeps its meaning as the lead time; the default and the
  user's setting change from 60 to 15. `0` disables the popup.
- While visible in the warning state, the window hides if the phase leaves
  work (pause, lock) or the remaining time jumps above the lead time
  (timer reset). A warning suppressed by a locked screen is not re-shown.

### "I didn't take this break" button

- On the "Break complete" screen a second button, "I didn't take this
  break", sits beside "I'm back — start the work timer".
- It performs the same scheduler transition as "I'm back" but records a new
  `missed` outcome instead of `taken`.
- `DailyStats` gains a `missed` counter, shown in the daily summary as
  "N missed", ordered after away and before skipped.

## Testing

Pure-helper tests cover the new `break_view` warning state, the `can_miss`
flag, the `missed` stats category and summary, and the changed default.
Behaviour is verified through the existing locale-pinned suite.
