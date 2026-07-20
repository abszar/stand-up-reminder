# Break Snooze and Skip Design

## Goal

Allow the user to defer an active standing-break reminder for five minutes or
skip that break entirely. Snoozing must bring back a fresh two-minute break
countdown, while skipping must immediately begin a fresh 30-minute work
interval.

## Scope and constraints

- Keep the fixed 30-minute work interval and two-minute break duration.
- Add a fixed five-minute snooze duration.
- Allow repeated snoozes.
- Measure snooze time using wall-clock time, including lock and suspend.
- Preserve the existing completed-break return-confirmation flow.
- Keep timing decisions in the deterministic scheduler rather than GTK.
- Do not add settings, duration controls, notifications, or persistence across
  application restarts.

## State model

Add a `SNOOZED` scheduler phase alongside `WORK`, `BREAK`, and
`AWAITING_RETURN`.

- `WORK` reaching zero starts `BREAK` with the full two-minute duration.
- Snoozing during `BREAK` enters `SNOOZED` with five minutes remaining and
  closes the popup.
- `SNOOZED` reaching zero starts a new `BREAK` with the full two-minute
  duration and opens the popup.
- Snoozing may be repeated each time the popup returns during `BREAK`.
- Skipping during `BREAK` enters `WORK` with the full 30-minute duration and
  closes the popup.
- `BREAK` reaching zero still enters `AWAITING_RETURN`. At that point the break
  has been completed, so snooze and skip are no longer available. The existing
  return action enters `WORK` with the full 30-minute duration.

The scheduler will expose explicit snooze and skip operations. Both operations
first account for elapsed time, then succeed only if the resulting phase is
still `BREAK`. This handles clicks at the exact countdown boundary safely: if
the break has already completed, the action is rejected and the
awaiting-return flow remains active.

## Timing behavior

The five-minute snooze always uses wall-clock elapsed time, independent of the
configured work timing mode. Lock and suspend therefore count toward the
snooze. If the snooze expires while the session is locked or suspended, the
scheduler moves to `BREAK`; the coordinator shows the popup as soon as the
session becomes available.

Entering a break after snooze resets both the break countdown to two minutes
and the away timer to zero. Time spent snoozing is not counted as break-away
time. Skipping resets the work interval at the exact click time.

## Popup interface

During `BREAK`, the popup shows two actions below the existing break content:

- **Give me 5 minutes** snoozes the reminder and closes the popup.
- **Skip this break** dismisses the current break and starts a fresh work
  interval.

Both actions are available on the initial popup and on every popup that
returns after a snooze. Once the countdown reaches zero, both actions are
hidden and the existing **I'm back — start 30-minute timer** action is shown.
The popup remains non-dismissible through window controls and Escape.

The two actions use distinct visual emphasis: snooze is the primary action and
skip is a quieter secondary action, reducing accidental break dismissal.

## Indicator interface

During `SNOOZED`, the status row displays `Break snoozed for MM:SS`, counting
down to the next popup. **Start break now** is disabled because a break is
already pending. The existing return/reset item follows its current safety
rule and cannot be used to bypass a pending break; it is disabled during both
`SNOOZED` and `BREAK`.

Other indicator states and timing-mode controls remain unchanged.

## Coordinator behavior

The GTK coordinator connects the popup buttons to the scheduler operations.
On a successful snooze or skip, it hides the popup and refreshes the indicator.
When snooze expiry emits the normal break-start transition, the coordinator
uses the existing popup-show path. Rejected actions leave the popup visible and
refresh its state so a boundary-time click cannot hide an already completed
break.

## Error and edge handling

- Snooze and skip calls outside `BREAK` are no-ops.
- A snooze or skip click processed after the break deadline cannot bypass the
  completed-break return requirement.
- Manual **Start break now** remains unavailable outside `WORK` and cannot
  restart a snooze or active break.
- Repeated timer ticks do not emit duplicate break-start transitions.
- Locking hides the break window as it does today; unlocking restores the
  current active or completed break state.

## Testing and verification

Scheduler tests will cover:

- snoozing an active break for exactly five wall-clock minutes;
- reopening with a fresh two-minute countdown;
- repeated snoozes;
- lock and suspend time counting toward snooze;
- overdue snooze behavior on unlock;
- skipping an active break and receiving a fresh 30-minute interval;
- rejecting snooze and skip outside `BREAK` and at the completion boundary;
- preserving existing break-completion and return behavior.

Presentation-helper tests will cover button visibility in `BREAK`, `SNOOZED`,
and `AWAITING_RETURN`, plus the snoozed indicator text where factored into pure
helpers. The complete unit-test suite will be run, followed by a short-duration
manual launch check when a graphical display is available.

## Out of scope

- Configurable snooze duration.
- A limit on the number of snoozes.
- Persisting snooze state after quitting or restarting the application.
- Changing the current return-confirmation behavior after a completed break.
