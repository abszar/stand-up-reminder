# Stand Up Reminder Design

## Goal

Build and install a lightweight native desktop application that prompts the
user to stand for two minutes after every 30 minutes of normal use. The
application must integrate with the Ubuntu GNOME top bar, start automatically
with each graphical login, remain easy to stop deliberately, and let the user
restart the work interval after returning from a longer break.

## Platform and constraints

- Target Ubuntu 24.04 with GNOME Shell 46 on X11.
- Use the already-installed Python 3, GTK 3, PyGObject, Ayatana AppIndicator,
  and Ubuntu AppIndicators GNOME extension.
- Do not require network access or new system packages.
- Install entirely for the current user; administrator access is unnecessary.
- Use fixed intervals: 30 minutes between breaks and 2 minutes per break.
- Provide an explicit Quit command. Quitting suppresses reminders until the
  user manually relaunches the app or begins a new graphical login.

## Architecture

The application is a single small Python/GTK process composed of three focused
units:

1. **Scheduler:** owns the current phase, deadlines, pause state, and
   transitions between work and break periods. It exposes deterministic logic
   that can be tested without starting GTK.
2. **Countdown window:** renders the active two-minute break, stays centered
   and above other windows, ignores ordinary close requests, and closes itself
   only when the countdown reaches zero or the whole application is explicitly
   quit from the indicator.
3. **Top-bar indicator:** reports time until the next break and offers Start
   break now, a long-break return reset, the sleep/lock timing policy, and
   Quit.

A small coordinator connects these units to GTK/GLib timers and GNOME session
lock events. User settings are stored in a JSON file below the XDG config
directory. A systemd user service tied to the graphical session launches the
application at login and restarts it after unexpected failures, but not after a
clean Quit.

## Timer behavior and data flow

On application launch, the scheduler begins a fresh 30-minute work interval.
When the interval expires, it enters the break phase and opens the countdown
window. Selecting Start break now cancels the current work deadline and enters
the same break phase immediately.

The break countdown begins at 02:00, updates once per second, and ends at
00:00. Completion closes the window and starts a completely new 30-minute work
interval. There is no snooze and no ordinary way to dismiss an active break.
The explicit top-bar Quit command remains an intentional escape hatch and may
stop the application even during a break.

The indicator's next-break label is updated during the work phase. While a
break is active, it reports that the break is in progress and disables the
manual-start command to prevent overlapping breaks.

Selecting **I'm back — restart 30-minute timer** during the work phase replaces
the partially elapsed work deadline with a fresh 30-minute interval. This is
intended for returning after a break that lasted longer than the enforced
two-minute countdown. Repeated selections always reset to a new full interval.
The action is disabled while the enforced break window is active so it cannot
be used to dismiss that window.

## Sleep and lock policy

The indicator provides two mutually exclusive policies, persisted between
launches:

- **Active time only:** the work interval pauses whenever the GNOME session is
  locked. Linux monotonic time naturally excludes system suspend, and the
  application explicitly excludes locked time. Unlocking resumes with the same
  amount of work time remaining.
- **Wall-clock time:** lock and suspend time count toward the work interval. If
  the deadline passes while the session cannot display the break window, the
  break begins immediately after the session unlocks or resumes.

Changing the policy preserves the currently displayed remaining time and uses
the new policy for subsequent elapsed time. The default is Active time only.
If the settings file is missing, malformed, or unreadable, the application
falls back to that default without failing to start.

## Countdown interface

The break window is a compact, centered card with:

- the title “Time to stand up”;
- a large `MM:SS` countdown;
- a short instruction to stand and move;
- no close button and no other controls.

It requests GTK's always-on-top behavior and remains centered on the active
display. Window-manager close requests, Escape, and Alt+F4 are ignored. At
00:00 it disappears automatically and the next work interval begins.

## Indicator interface

The always-visible GNOME top-bar indicator opens a compact menu containing:

- a disabled status row showing the next break countdown or “Break in
  progress”;
- **Start break now**;
- **I'm back — restart 30-minute timer**, enabled only during the work phase;
- a sleep/lock timing submenu with **Active time only** and **Wall-clock
  time**;
- **Quit**.

The same application is also installed in the GNOME Applications menu so it
can be relaunched after Quit.

## Startup, shutdown, and failure handling

The installation enables a user-level service associated with the graphical
session. The service starts the application at graphical login. Unexpected
nonzero exits are restarted. The Quit action performs a normal zero exit, so
the service does not immediately restart it. It will start again when a new
graphical login begins.

Only one instance may own the application identifier. Launching it again while
it is already running activates the existing process instead of creating a
second schedule or a second indicator.

Errors reading settings use safe defaults. Errors writing settings leave the
current in-memory choice operational and are logged to the user journal. GTK,
indicator, or session-integration startup failures are also logged before a
nonzero exit allows the service to retry.

## Testing and verification

Automated tests cover the scheduler separately from the graphical interface:

- initial 30-minute deadline;
- scheduled and manual transitions into a break;
- the exact two-minute countdown and 30-minute reset after completion;
- duplicate manual-start prevention;
- active-time pause/resume across locking;
- wall-clock overdue behavior after unlock or resume;
- long-break return resets after partially elapsed work intervals;
- repeated long-break return resets and exact-deadline behavior;
- policy changes preserving remaining time;
- malformed settings fallback.

Integration checks verify the installed files, service enablement, single
instance behavior, clean Quit versus crash restart, and Applications-menu
entry. A short-duration test mode is used during manual verification to confirm
that the countdown is centered, always on top, non-dismissible through normal
window controls, and followed by a newly reset work interval.

## Out of scope

- Custom work or break durations.
- Snoozing or dismissing an active break through normal window controls.
- Usage statistics, accounts, cloud synchronization, sounds, and mobile
  notifications.
- Automatic detection of long breaks or idle periods.
- Supporting desktop environments other than the installed Ubuntu GNOME/X11
  session.
