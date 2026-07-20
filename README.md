# Stand Up Reminder

Stand Up Reminder is a native Ubuntu Linux application for GNOME that prompts
you to take a two-minute standing break after every 30 minutes of work. It runs
as a lightweight GTK application with a top-bar indicator and an always-on-top
break window.

## Features

- Fixed 30-minute work intervals and two-minute standing breaks.
- **Give me 5 minutes** snooze that can be repeated and returns with a fresh
  two-minute countdown.
- **Skip this break** action that immediately starts a new work interval.
- Explicit return confirmation after a completed break.
- Active-time or wall-clock handling for lock and suspend periods.
- GNOME top-bar status and controls.
- Automatic startup at graphical login.
- User-local application installation.

## Compatibility

Tested on Ubuntu 24.04 LTS, GNOME Shell 46, and X11. Other Ubuntu releases,
GNOME versions, Wayland sessions, and desktop environments are not verified.

## Install on Ubuntu

### 1. Install system dependencies

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
  desktop-file-utils
```

### 2. Clone and install

```bash
git clone https://github.com/abszar/stand-up-reminder.git
cd stand-up-reminder
scripts/install.sh
```

The installer copies the application into user-local directories, installs
the launcher and icons, configures login startup, and starts the user service.

### 3. Verify it is running

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

Open the top-bar indicator to see the next break, start a break immediately,
restart after a longer absence, select lock/suspend timing, or quit.

During the two-minute countdown:

- **Give me 5 minutes** returns five wall-clock minutes later with a fresh
  two-minute countdown and can be repeated.
- **Skip this break** immediately starts a fresh 30-minute work interval.

At `00:00`, the popup changes to **Break complete** and shows
**I'm back — start 30-minute timer**. Work resumes when return is confirmed.

## Timing modes

- **Active time only** pauses work timing while locked and excludes suspend.
- **Wall-clock time** counts lock and suspend; overdue breaks start when the
  session becomes available.

Snooze and break countdowns always use wall-clock time.

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
autostart entry, service file, and icons from user directories.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Short durations can be supplied with `STAND_UP_REMINDER_WORK_SECONDS`,
`STAND_UP_REMINDER_BREAK_SECONDS`, and
`STAND_UP_REMINDER_SNOOZE_SECONDS`.

## License

Stand Up Reminder is available under the [MIT License](LICENSE).
