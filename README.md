# Stand Up Reminder

A native Ubuntu GNOME reminder that starts a two-minute standing break after
every 30 minutes of work.

## Controls

Click the top-bar icon to see the next break, start a break immediately, mark
your return from a longer break, choose whether lock/suspend time counts, or
quit the application. During the two-minute countdown, **Give me 5 minutes**
closes the popup and brings it back five wall-clock minutes later with a fresh
two-minute countdown. Snoozing can be repeated. **Skip this break** closes the
popup and immediately starts a fresh 30-minute work interval.

When a break is allowed to finish, the centered always-on-top popup changes to
**Break complete** and reveals **I'm back — start 30-minute timer**. Click that
button when you return to close the popup and begin a fresh work interval.

The top-bar **I'm back — restart 30-minute timer** action performs the same
return confirmation after the minimum finishes. It remains unavailable during
the enforced countdown. Quit is the deliberate way to stop the app.

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
