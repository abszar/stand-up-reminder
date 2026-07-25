# Day timeline on the break and statistics popups

Date: 2026-07-25. Requested by Abdelali ("a colored bar or dots design").

## Design

- `StatsStore.record` also appends `["HH:MM", outcome]` to an `events`
  list in the day's entry; reading is tolerant (missing list, malformed
  pairs, and out-of-range times are skipped). Old days simply have no
  events.
- `timeline_layout(events, now_minutes)` (pure, tested) maps events to
  fractions on a track that spans whole hours from the first event (or the
  current hour on a quiet day) to the later of the last event and now.
- `TimelineStrip`, a small cairo `Gtk.DrawingArea`, draws the track and
  one dot per outcome: green taken, gray-teal away, red missed, orange
  skipped, pale snoozed.
- The break window shows a thin strip above the score line, refreshed with
  the score line and additionally just before the window is shown, so the
  "now" end of the track is current.
- The statistics popup shows a taller strip with the track's start and end
  times underneath and a color legend.
- The Debian package gains a `python3-gi-cairo` dependency for the
  drawing-area cairo context.
