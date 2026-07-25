# Changelog

All notable changes to Stand Up Reminder are documented in this file.

## [Unreleased]

### Added

- A day timeline on the break window and the statistics popup: each
  recorded outcome is stored with its time and drawn as a colored dot on a
  track spanning the worked part of the day (green taken, gray-teal away,
  red missed, orange skipped, pale snoozed). The statistics popup adds the
  track's start and end times and a color legend. The whole timeline block
  stays hidden until the day has its first recorded outcome.
- The statistics popup carries the mood emoji beside its score, labels that
  score as the week's, and adds today's score on its own line.

## [1.2.0] - 2026-07-25

### Added

- The break window shows the day's and the week's adherence scores with a
  mood emoji, e.g. "Today: 75% 🙂 · This week: 92% 😄".
- A **Statistics** entry in the indicator menu that opens a popup styled
  like the break card, showing today's counters, the last seven days with a
  per-day row of breaks taken, and a weekly adherence score (breaks taken
  against missed and skipped) with a one-line verdict.
- An **I didn't take this break** button beside the return confirmation, for
  breaks that finished while working elsewhere. It restarts the work timer
  and counts the break as missed, a new category in the daily summary.

### Changed

- The pre-break desktop notification is replaced by the break window itself,
  which now opens 15 seconds before the break with a live countdown and the
  message "Time to stand up in 0:15".

- Time away from the keyboard now counts as a break only after a configurable
  threshold (10 minutes by default, chosen from the Options menu) instead of
  after a single break length. Short pauses — reading, a phone call, working
  on another computer — no longer silently restart the work timer.
- Breaks credited for time away are counted separately from breaks taken, so
  the daily summary reflects only the breaks that were really taken.

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
