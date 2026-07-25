# Statistics popup

Date: 2026-07-25. Approved by Abdelali.

## Problem

Daily counters only appear as one line in the tray menu. The user wants a
proper statistics view: today, the week, and an assessment of how well
breaks were kept.

## Design

### Data (stats.py, pure and tested)

- `last_days(count, today)` — ISO day keys in chronological order ending
  today (rolling window; the week is the last 7 days).
- `StatsStore.load_days(days)` — stats for several days from one file read.
- `aggregate_stats(iterable)` — field-wise sum of `DailyStats`.
- `adherence_percent(stats)` — `round(100 * taken / (taken + missed +
  skipped))`, or `None` when no breaks were due. Away credits and snoozes
  are neutral: on a two-PC desk idle time proves nothing, and a snooze
  always resolves into another outcome.
- `rating_label(percent)` — verdict text: `None` "no breaks due", >=90
  excellent, >=70 good, >=40 could be better, else a nudge to stand up
  more often.
- `summary_label` refactors its outcome list into a shared helper also
  used by a new `week_label` ("This week: ...").

### Window (application.py)

- `StatsWindow`, opened from a new "Statistics" tray-menu item under the
  daily summary line. Same visual language as the break card (dark green,
  orange accents, monospace numbers), default size 560x540, undecorated,
  keep-above, centered.
- Closable, unlike the break window: Close button, Escape, or delete-event
  all hide it (the instance is reused).
- Content: eyebrow "STATISTICS"; the today summary line; the week summary
  line; a 7-column grid of weekday abbreviation over breaks taken that
  day; the week's adherence percentage in large type with the verdict
  underneath.
- Data refreshes when the item opens the window and whenever an outcome is
  recorded while it is visible.

## Follow-up (same day): scores on the break window

Every state of the break window carries a bottom line with the day and
week adherence and a mood emoji per rating tier ("Today: 75% 🙂 · This
week: 92% 😄", em dash when nothing was due). `score_line` lives in
stats.py; the application recomputes it when an outcome is recorded and
when the day rolls over, not on every refresh tick.

## Testing

Pure helpers are fully covered in tests/test_stats.py under the C locale.
The window follows the existing untested-GTK pattern of BreakWindow.
