# Stand Up Reminder

A native Ubuntu GNOME reminder that starts a two-minute standing break after
every 30 minutes of work.

## Controls

Click the top-bar icon to see the next break, start a break immediately, mark
your return from a longer break, choose whether lock/suspend time counts, or
quit the application. Use **I'm back — restart 30-minute timer** after returning
to begin a fresh work interval; it is unavailable during the enforced
countdown. An active break is centered, always on top, and cannot be closed
through normal window controls. Quit remains the deliberate way to stop the app.

## Timing modes

- **Active time only** pauses the work timer during lock and suspend.
- **Wall-clock time** counts lock and suspend; an overdue break starts after
  the session becomes available.

## Startup and relaunch

The app starts at every graphical login. Quit keeps it stopped for the current
login. Launch **Stand Up Reminder** from the Applications menu to start it
again.

## Development

Run tests with:

```bash
python3 -m unittest discover -s tests -v
```

Install or update with `scripts/install.sh`. Remove the application with
`scripts/uninstall.sh`.
