# Changelog

All notable changes to Stand Up Reminder are documented in this file.

## [1.1.0] - 2026-07-21

### Added

- Configurable work interval and break length, chosen from the indicator menu
  and stored with the rest of the settings.
- Countdown to the next break beside the top-bar icon, which can be hidden.
- Desktop notification shortly before a break begins.
- Pausing for 30 minutes, an hour, or until reminders are resumed.
- Idle detection that counts a long stretch away from the keyboard as a break
  already taken.
- Daily counts of breaks taken, skipped, and snoozed, shown in the menu and
  kept for 30 days.
- Keyboard shortcuts in the break window: `S` to snooze, `K` to skip, and
  `Enter` to confirm a return.
- Optional sound cues at the start and end of a break.
- Dimming of monitors that are not showing the break window.
- French translation and a gettext workflow for adding more languages.
- Debian package build, a locale-pinned test runner, and continuous
  integration covering tests, shell scripts, catalogues, and packaging.

### Changed

- The break window opens fullscreen on Wayland, which does not allow an
  application to place a window or keep it above others.
- The launcher is installed as `io.github.abdelali.StandUpReminder.desktop`
  so that GNOME attributes break notifications to the application. Installing
  removes the previous launcher name.
- Settings are read field by field, so one unusable value no longer discards
  the rest of the configuration.

## [1.0.0] - 2026-07-20

### Added

- Native Ubuntu GNOME top-bar indicator and centered standing-break window.
- Deterministic 30-minute work and two-minute break cycle.
- Repeatable five-minute snoozing and full-break skipping.
- Explicit return confirmation after a completed break.
- Active-time and wall-clock timing modes for lock and suspend behavior.
- Graphical-login startup, Applications menu launcher, and clean Quit flow.
- User-local install, update, and uninstall scripts.
- Automated scheduler, presentation, settings, and installation tests.
