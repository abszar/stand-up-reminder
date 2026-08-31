# Stand Up Reminder

Stand Up Reminder is a native Ubuntu Linux application for GNOME that prompts
you to take a standing break after each work interval. It runs as a
lightweight GTK application with a top-bar indicator and an always-on-top
break window.

## Look

The interface is an 8-bit pixel HUD: one eleven-colour palette, a bitmap face
(Silkscreen, shipped with the application), display digits drawn as sprites,
and hard four-pixel frames with cut corners. Nothing eases — the countdown
blinks and shudders, the progress bar dies a cell at a time, the card wipes
open in six bands, and a mint burst marks a break you kept. Every motion is
dropped when the desktop asks for reduced animation, though the colours that
carry urgency, success and failure always stay.

## Features

- Configurable work intervals and break lengths, defaulting to a 30-minute
  interval and a two-minute break.
- Countdown to the next break shown next to the top-bar icon.
- The break window opens 15 seconds early with a countdown that reddens as
  the break approaches, offering the same snooze and skip actions.
- **Pause reminders** for 30 minutes, an hour, or until you resume.
- Repeatable snooze that returns with a fresh break countdown.
- **Skip this break** action that immediately starts a new work interval.
- **Standing mode** for standing desks: answer the break by standing, and
  a small pill on the right edge counts how long you have been up. Drag it
  up or down the edge; it reopens where you left it, and closes when you
  sit back down.
- Explicit return confirmation after a completed break, with an
  **I didn't take this break** button for breaks that slipped by.
- Long stretches away from the keyboard count as a break already taken, after
  a configurable threshold (10 minutes by default).
- Daily counts of breaks taken, time-away credits, missed, skipped, and
  snoozed.
- A **Score** window with the week's adherence in sprite digits, a verdict,
  the day timeline, and twelve weeks of tiles; the break card carries the day
  and week scores beside a face whose colour is the verdict.
- A day timeline on both surfaces: one colored mark per break outcome, placed
  by time of day, with a bone mark for now.
- A contribution-style grid of the last twelve weeks, each day shaded by
  how well its breaks were kept.
- A pixel **control window**, opened from the top-bar menu, carrying every
  action: start a break, restart the timer, start or stop the standing
  counter, pause, and the score, settings and quit.
- A **Settings** panel in the same pixel language for the durations, the
  counting rules and the away credit, which keeps the top-bar menu down to
  the handful of actions you use while working.
- **Eye breaks** on their own clock: every twenty minutes a small card asks
  for twenty seconds and then closes itself. It never dims, never takes
  focus, and never lands on top of a break card. Three prompts share the
  rotation — look out a window, close your eyes for three firm squeezes and
  a rest, and walk your eyes around a ring — weighted towards looking into
  the distance, which is the part with the clearest evidence behind it.
- **Discreet mode**, a switch in the top-bar menu for when somebody else is
  watching your screen. The break moves to a small card in the bottom right
  corner, the dimmer is dropped, eye cards are held back and the application
  goes silent. It changes no setting and resets to normal when the
  application restarts.
- Chiptune sound cues shipped with the application: a call when the break
  arrives, a settle when it is over, a fanfare for a break kept, and one per
  eye prompt. A master switch silences everything; each cue also has a row
  of its own.
- Keyboard shortcuts.
- Other monitors dim while the break window is showing (except in Discreet
  mode).
- Active-time or wall-clock handling for lock and suspend periods.
- Automatic startup at graphical login.
- English and French interface text.

## Compatibility

Tested on Ubuntu 24.04 LTS, GNOME Shell 46, and X11. Other Ubuntu releases,
GNOME versions, and desktop environments are not verified.

On Wayland the break window opens fullscreen, because Wayland does not let an
application place a window or force it above others. The top-bar indicator and
the rest of the interface are unchanged, but this path has not been verified on
a Wayland session.

## Install on Ubuntu

### Option 1: Debian package

```bash
scripts/build-deb.sh
sudo apt install ./dist/stand-up-reminder_*_all.deb
```

This installs the application system-wide, pulls in its dependencies, and
starts it for every user at graphical login.

### Option 2: User-local install

#### 1. Install system dependencies

Application files are installed for the current user; installing the required
Ubuntu packages uses `sudo`.

```bash
sudo apt update
sudo apt install \
  git \
  python3 \
  python3-gi \
  gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 \
  gnome-shell-extension-appindicator \
  desktop-file-utils \
  gettext
```

The sounds shipped with the application play through `paplay` or `aplay`,
which Ubuntu already has. Installing `gir1.2-gsound-1.0` routes them through
GSound instead, which is only needed for cues drawn from the desktop's own
sound theme.

#### 2. Clone and install

```bash
git clone https://github.com/abszar/stand-up-reminder.git
cd stand-up-reminder
scripts/install.sh
```

The installer copies the application into user-local directories, compiles the
translations, installs the launcher and icons, configures login startup, and
starts the user service.

#### 3. Verify it is running

```bash
systemctl --user status stand-up-reminder.service
```

The service should report `active (running)`, and the icon should appear in
the GNOME top bar.

## Update an existing installation

```bash
git pull --ff-only
scripts/install.sh
```

The installer replaces the user-local copy and restarts the service.

## Controls

Open the top-bar indicator to see the next break and today's break count,
start a break immediately, restart after a longer absence, pause reminders,
change durations, select lock/suspend timing, or quit.

During the break countdown:

- **Give me 5 minutes** returns five wall-clock minutes later with a fresh
  break countdown and can be repeated. `S` does the same.
- **Skip this break** immediately starts a fresh work interval. `K` does the
  same.

At `00:00`, the popup changes to **Break complete** and shows
**I'm back**. Work resumes when return is confirmed, with `Enter` or the
button. `Esc` does not dismiss the break.

## Settings

Durations, timing mode, and the options below are set from the Settings panel
in the control window and stored in
`~/.config/stand-up-reminder/settings.json`. Values outside the
menu presets can be set by editing that file; out-of-range values are clamped
when it is read.

| Setting | Meaning |
| --- | --- |
| `work_seconds` | Length of a work interval |
| `break_seconds` | Length of an enforced break |
| `snooze_seconds` | Delay added by the snooze button |
| `warning_seconds` | Pre-break countdown lead time; `0` disables it |
| `idle_credit_seconds` | Idle time before an absence counts as a break; never shorter than the break length |
| `idle_reset_enabled` | Count time away from the keyboard as a break |
| `show_countdown` | Show the countdown next to the top-bar icon |
| `sound_enabled` | Master switch for every sound the application makes |
| `muted_sounds` | Names of individual cues to silence, e.g. `["break_done"]` |
| `eye_breaks_enabled` | Show the eye-break card on a timer |
| `eye_interval_seconds` | How often an eye card appears; 15, 20 or 30 minutes |
| `muted_prompts` | Eye prompts to skip, from `far`, `shut` and `move` |
| `eye_rotation_index` | Where the eye prompt rotation has got to |
| `standing_pill_position` | Where the standing pill sits on the right edge |
| `timing_mode` | `active` or `wall`, described below |

Daily break counts are kept in
`~/.local/share/stand-up-reminder/stats.json` for the last twelve weeks.
Individual break times, which feed the day timeline, are kept for the last
week only.

## Timing modes

- **Active time only** pauses work timing while locked and excludes suspend.
- **Wall-clock time** counts lock and suspend; overdue breaks start when the
  session becomes available.

Snooze, pause, and break countdowns always use wall-clock time.

## Startup, Quit, and relaunch

The application starts automatically at graphical login. **Quit** keeps it
stopped for the current login. Relaunch it from GNOME Applications or run:

```bash
systemctl --user start stand-up-reminder.service
```

## Troubleshooting

### The service does not start

Inspect its current state and recent log messages:

```bash
systemctl --user status stand-up-reminder.service
journalctl --user -u stand-up-reminder.service -n 100 --no-pager
```

After correcting the reported problem, restart it:

```bash
systemctl --user restart stand-up-reminder.service
```

### The top-bar icon is missing

Confirm that `gnome-shell-extension-appindicator` is installed and that the
AppIndicator extension is enabled in the current GNOME session:

```bash
gnome-extensions list --enabled | grep -i appindicator
```

After installing or enabling the extension, sign out and back in so GNOME
loads it for the new session. The documented top-bar integration is verified
on GNOME Shell 46 with X11; Wayland and other desktop sessions are unverified.

### Python reports `No module named 'gi'`

Install the required Python and GI packages, then rerun `scripts/install.sh`:

```bash
sudo apt install \
  python3-gi \
  gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1
```

## Uninstall

```bash
scripts/uninstall.sh
```

This stops the service and removes the installed application, launcher,
autostart entry, service file, icons, and translations from user directories.
Settings and statistics are left in place; remove
`~/.config/stand-up-reminder` and `~/.local/share/stand-up-reminder` to
discard them.

For the Debian package:

```bash
sudo apt remove stand-up-reminder
```

## Development

```bash
scripts/run-tests.sh
```

The runner pins the C locale so that the tests, which assert untranslated
strings, pass on a translated desktop.

Short durations can be supplied with `STAND_UP_REMINDER_WORK_SECONDS`,
`STAND_UP_REMINDER_BREAK_SECONDS`, and
`STAND_UP_REMINDER_SNOOZE_SECONDS`, which override the stored settings.

### Translations

Interface strings are translated with gettext. After changing any string:

```bash
scripts/update-translations.sh
```

This refreshes `po/stand-up-reminder.pot` and merges it into each catalogue.
To start a new language, run
`msginit --locale=<code> --input=po/stand-up-reminder.pot --output=po/<code>.po`
and translate the result. `scripts/install.sh` compiles every catalogue.

## License

Stand Up Reminder is available under the [MIT License](LICENSE).
