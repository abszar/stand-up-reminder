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

1. **Scheduler:** owns deadlines, lock state, wall-clock absence time, and
   three explicit phases: work, enforced two-minute countdown, and awaiting
   return. It exposes deterministic logic that can be tested without GTK.
2. **Countdown window:** renders the minimum two-minute countdown and a
   wall-clock “Away for” count-up. It remains centered and above other windows
   after the minimum finishes, then closes only after explicit return
   confirmation or application Quit.
3. **Top-bar indicator:** reports time until the next break, break progress, or
   total absence and offers Start break now, return confirmation, the sleep/lock
   timing policy, and Quit.

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

The break countdown begins at 02:00 while a separate “Away for” timer counts
up from 00:00. Reaching 00:00 completes the enforced minimum but does not close
the popup or begin work. The scheduler enters an awaiting-return phase, the
popup changes its main message to “Break complete,” and the away timer
continues to show total wall-clock absence.

An **I'm back — start 30-minute timer** button appears in the popup only after
the enforced minimum finishes. Confirming return closes the popup and begins a
fresh 30-minute interval at that exact moment. Before then, no normal control
can dismiss the popup. Application Quit remains an intentional escape hatch.

The indicator reports the next-break countdown during work, “Break in
progress” during the enforced minimum, and total absence while awaiting return.
Start break now is disabled outside work. The top-bar **I'm back — restart
30-minute timer** action remains disabled during the enforced minimum, becomes
a return confirmation while awaiting return, and resets a partially elapsed
work deadline when selected during work.

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
the new policy for subsequent work time. The default is Active time only. If
the settings file is missing, malformed, or unreadable, the application falls
back to that default without failing to start.

Break countdown and absence timing always use wall-clock time, independent of
the work timing policy. Lock and suspend therefore count toward total absence.
The window hides behind the lock screen and reappears after unlock with the
correct countdown or awaiting-return state.

## Countdown interface

The break window is a compact, centered card with:

- the title “Time to stand up” during the minimum and “Break complete” after it;
- a large `MM:SS` countdown during the enforced two minutes;
- an “Away for MM:SS” count-up visible from the start;
- a short instruction to stand and move;
- an **I'm back — start 30-minute timer** button that appears only after 00:00;
- no close button.

It requests GTK's always-on-top behavior and remains centered on the active
display. Window-manager close requests, Escape, and Alt+F4 are ignored
throughout both break phases. At 00:00 the popup stays open, the count-up
continues, and only explicit return confirmation begins the next work interval.

## Indicator interface

The always-visible GNOME top-bar indicator opens a compact menu containing:

- a disabled status row showing the next-break countdown, “Break in
  progress,” or “Away for MM:SS”;
- **Start break now**, enabled only during work;
- **I'm back — restart 30-minute timer**, disabled during the enforced minimum
  and enabled during work or while awaiting return;
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
- exact two-minute minimum without automatic work restart;
- wall-clock absence count-up from break start through lock and suspend;
- return confirmation rejected before the minimum and accepted afterward;
- 30-minute reset beginning at the return-confirmation moment;
- duplicate manual-start prevention;
- active-time pause/resume across locking;
- wall-clock overdue behavior after unlock or resume;
- long-break return resets during partially elapsed work intervals;
- repeated resets and exact-deadline behavior;
- policy changes preserving remaining work time;
- malformed settings fallback.

Integration checks verify installed files, service startup, single-instance
behavior, clean Quit, and the Applications entry. Short-duration live
verification confirms the popup remains always on top after 00:00, the away
timer continues, the return button appears only after the minimum, and
confirming return closes the popup and starts a fresh work interval.

## Out of scope

- Custom work or break durations.
- Snoozing or dismissing an active break through normal window controls.
- Usage statistics, accounts, cloud synchronization, sounds, and mobile
  notifications.
- Automatic detection of long breaks or idle periods.
- Supporting desktop environments other than the installed Ubuntu GNOME/X11
  session.
