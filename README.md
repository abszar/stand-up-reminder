# Stand Up Reminder

Stand Up Reminder is a native Ubuntu Linux application for GNOME that prompts
you to take a standing break after each work interval. It runs as a
lightweight GTK application with a top-bar indicator and an always-on-top
break window.

## Features

- Configurable work intervals and break lengths, defaulting to a 30-minute
  interval and a two-minute break.
- Countdown to the next break shown next to the top-bar icon.
- Desktop notification one minute before a break begins.
- **Pause reminders** for 30 minutes, an hour, or until you resume.
- Repeatable snooze that returns with a fresh break countdown.
- **Skip this break** action that immediately starts a new work interval.
- Explicit return confirmation after a completed break.
- Long stretches away from the keyboard count as a break already taken.
- Daily counts of breaks taken, skipped, and snoozed.
- Keyboard shortcuts and optional sound cues.
- Other monitors dim while the break window is showing.
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

Sound cues additionally require `gir1.2-gsound-1.0`. Without it the
application runs normally and the sound option has no effect.

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

Durations, timing mode, and the options below are set from the indicator menu
and stored in `~/.config/stand-up-reminder/settings.json`. Values outside the
menu presets can be set by editing that file; out-of-range values are clamped
when it is read.

| Setting | Meaning |
| --- | --- |
| `work_seconds` | Length of a work interval |
| `break_seconds` | Length of an enforced break |
| `snooze_seconds` | Delay added by the snooze button |
| `warning_seconds` | Notification lead time; `0` disables it |
| `idle_reset_enabled` | Count time away from the keyboard as a break |
| `show_countdown` | Show the countdown next to the top-bar icon |
| `sound_enabled` | Play a sound when a break starts and ends |
| `timing_mode` | `active` or `wall`, described below |

Daily break counts are kept in
`~/.local/share/stand-up-reminder/stats.json` for the last 30 days.

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
