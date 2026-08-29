import json
import tempfile
import unittest
from pathlib import Path

from stand_up_reminder.stats import (
    HISTORY_DAYS,
    BreakOutcome,
    DailyStats,
    StatsStore,
    HEAT_LEVELS,
    adherence_percent,
    aggregate_stats,
    day_tooltip,
    heat_level,
    heatmap_weeks,
    last_days,
    rating_label,
    score_headline,
    score_line,
    summary_label,
    timeline_layout,
    week_label,
)


class SummaryLabelTests(unittest.TestCase):
    def test_reports_a_quiet_day(self):
        self.assertEqual(summary_label(DailyStats()), "Nothing recorded yet")

    def test_reports_only_the_outcomes_that_happened(self):
        self.assertEqual(
            summary_label(DailyStats(taken=1)), "Today  1 taken"
        )
        self.assertEqual(
            summary_label(DailyStats(taken=4, skipped=2)),
            "Today  4 taken · 2 skipped",
        )

    def test_reports_every_outcome(self):
        self.assertEqual(
            summary_label(
                DailyStats(taken=3, away=2, missed=4, skipped=1, snoozed=5)
            ),
            "Today  3 taken · 2 away · 4 missed · 1 skipped · 5 snoozed",
        )

    def test_reports_a_day_with_only_missed_breaks(self):
        self.assertEqual(summary_label(DailyStats(missed=2)), "Today  2 missed")

    def test_reports_a_day_with_only_away_credits(self):
        self.assertEqual(summary_label(DailyStats(away=4)), "Today  4 away")


class WeekLabelTests(unittest.TestCase):
    def test_reports_a_quiet_week(self):
        self.assertEqual(week_label(DailyStats()), "Nothing recorded this week")

    def test_reports_the_week_outcomes(self):
        self.assertEqual(
            week_label(DailyStats(taken=12, missed=3)),
            "Week  12 taken · 3 missed",
        )


class LastDaysTests(unittest.TestCase):
    def test_lists_the_window_ending_today_in_order(self):
        self.assertEqual(
            last_days(7, "2026-07-25"),
            [
                "2026-07-19",
                "2026-07-20",
                "2026-07-21",
                "2026-07-22",
                "2026-07-23",
                "2026-07-24",
                "2026-07-25",
            ],
        )

    def test_crosses_month_boundaries(self):
        self.assertEqual(last_days(3, "2026-08-01"), ["2026-07-30", "2026-07-31", "2026-08-01"])


class AggregateStatsTests(unittest.TestCase):
    def test_sums_every_counter(self):
        total = aggregate_stats(
            [
                DailyStats(taken=1, away=2, missed=3, skipped=4, snoozed=5),
                DailyStats(taken=10, snoozed=1),
            ]
        )
        self.assertEqual(
            total, DailyStats(taken=11, away=2, missed=3, skipped=4, snoozed=6)
        )

    def test_sums_nothing_to_an_empty_day(self):
        self.assertEqual(aggregate_stats([]), DailyStats())


class AdherenceTests(unittest.TestCase):
    def test_scores_taken_against_missed_and_skipped(self):
        self.assertEqual(adherence_percent(DailyStats(taken=9, missed=1)), 90)
        self.assertEqual(
            adherence_percent(DailyStats(taken=1, missed=1, skipped=2)), 25
        )

    def test_away_and_snoozed_are_neutral(self):
        self.assertEqual(
            adherence_percent(DailyStats(taken=1, away=9, snoozed=9)), 100
        )

    def test_no_due_breaks_has_no_score(self):
        self.assertIsNone(adherence_percent(DailyStats()))
        self.assertIsNone(adherence_percent(DailyStats(away=5)))


class RatingLabelTests(unittest.TestCase):
    def test_rates_each_tier(self):
        self.assertEqual(rating_label(None), "Nothing due yet today.")
        self.assertEqual(rating_label(100), "Great week. You barely miss one.")
        self.assertEqual(rating_label(85), "Great week. You barely miss one.")
        self.assertEqual(rating_label(70), "Good week. Most breaks taken.")
        self.assertEqual(rating_label(50), "Half of them slipped by.")
        self.assertEqual(rating_label(49), "Let's get more of these.")


class ScoreHeadlineTests(unittest.TestCase):
    def test_pairs_the_percentage_with_its_mood(self):
        self.assertEqual(score_headline(95), "95%")
        self.assertEqual(score_headline(70), "70%")
        self.assertEqual(score_headline(40), "40%")
        self.assertEqual(score_headline(5), "5%")

    def test_shows_a_dash_when_no_breaks_were_due(self):
        self.assertEqual(score_headline(None), "—")


class ScoreLineTests(unittest.TestCase):
    def test_shows_both_scores_with_their_mood(self):
        self.assertEqual(
            score_line(75, 92), "Today 75% · Week 92%"
        )
        self.assertEqual(
            score_line(40, 20), "Today 40% · Week 20%"
        )

    def test_shows_a_dash_when_no_breaks_were_due(self):
        self.assertEqual(score_line(None, None), "Today — · Week —")
        self.assertEqual(score_line(None, 100), "Today — · Week 100%")


class HeatLevelTests(unittest.TestCase):
    def test_shades_a_day_by_its_adherence(self):
        self.assertEqual(heat_level(DailyStats(taken=10)), HEAT_LEVELS - 1)
        self.assertEqual(heat_level(DailyStats(taken=8, missed=2)), 2)
        self.assertEqual(heat_level(DailyStats(taken=1, missed=1)), 1)
        self.assertEqual(heat_level(DailyStats(taken=1, missed=9)), 0)

    def test_a_day_without_due_breaks_has_no_level(self):
        self.assertIsNone(heat_level(DailyStats()))
        self.assertIsNone(heat_level(DailyStats(away=3, snoozed=1)))


class DayTooltipTests(unittest.TestCase):
    def test_names_the_day_with_its_counts_and_score(self):
        self.assertEqual(
            day_tooltip("2026-07-31", DailyStats(taken=9, missed=1)),
            "FRI 31 JUL\n9 taken · 1 missed",
        )

    def test_reports_a_day_without_breaks(self):
        self.assertEqual(
            day_tooltip("2026-07-26", DailyStats()), "SUN 26 JUL\nNothing recorded"
        )


class HeatmapWeeksTests(unittest.TestCase):
    def test_arranges_days_into_sunday_first_columns(self):
        # 2026-07-26 is a Sunday, so it opens a fresh column.
        weeks = heatmap_weeks(["2026-07-26", "2026-07-27", "2026-07-31"])
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0][0], "2026-07-26")
        self.assertEqual(weeks[0][1], "2026-07-27")
        self.assertEqual(weeks[0][5], "2026-07-31")
        self.assertIsNone(weeks[0][2])
        self.assertIsNone(weeks[0][6])

    def test_pads_the_first_column_before_the_opening_weekday(self):
        # 2026-07-31 is a Friday: rows above it stay empty.
        weeks = heatmap_weeks(["2026-07-31", "2026-08-01", "2026-08-02"])
        self.assertEqual(len(weeks), 2)
        self.assertEqual(weeks[0][:5], [None] * 5)
        self.assertEqual(weeks[0][5], "2026-07-31")
        self.assertEqual(weeks[0][6], "2026-08-01")
        self.assertEqual(weeks[1][0], "2026-08-02")

    def test_every_column_holds_a_full_week(self):
        weeks = heatmap_weeks(last_days(35, "2026-07-31"))
        self.assertEqual(len(weeks), 6)
        for column in weeks:
            self.assertEqual(len(column), 7)
        placed = [day for column in weeks for day in column if day]
        self.assertEqual(len(placed), 35)
        self.assertEqual(placed[-1], "2026-07-31")

    def test_no_days_makes_no_columns(self):
        self.assertEqual(heatmap_weeks([]), [])


class TimelineLayoutTests(unittest.TestCase):
    def test_places_events_between_the_first_hour_and_now(self):
        start, end, points = timeline_layout(
            [(9 * 60 + 30, "taken"), (10 * 60, "missed")], now_minutes=10 * 60 + 30
        )
        self.assertEqual(start, 9 * 60)
        self.assertEqual(end, 11 * 60)
        self.assertEqual(points, [(0.25, "taken"), (0.5, "missed")])

    def test_an_empty_day_spans_the_current_hour(self):
        start, end, points = timeline_layout([], now_minutes=10 * 60 + 15)
        self.assertEqual(start, 10 * 60)
        self.assertEqual(end, 11 * 60)
        self.assertEqual(points, [])

    def test_the_track_stretches_to_cover_every_event(self):
        _start, _end, points = timeline_layout(
            [(8 * 60, "taken"), (19 * 60, "missed")], now_minutes=12 * 60
        )
        for fraction, _outcome in points:
            self.assertGreaterEqual(fraction, 0.0)
            self.assertLessEqual(fraction, 1.0)


class StatsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "nested" / "stats.json"
        self.store = StatsStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_file_reports_an_empty_day(self):
        self.assertEqual(self.store.load("2026-07-20"), DailyStats())

    def test_records_accumulate_within_a_day(self):
        self.store.record(BreakOutcome.TAKEN, "2026-07-20")
        self.store.record(BreakOutcome.TAKEN, "2026-07-20")
        self.store.record(BreakOutcome.SKIPPED, "2026-07-20")
        self.assertEqual(
            self.store.load("2026-07-20"), DailyStats(taken=2, skipped=1)
        )

    def test_away_credits_are_counted_apart_from_taken_breaks(self):
        self.store.record(BreakOutcome.TAKEN, "2026-07-20")
        self.store.record(BreakOutcome.AWAY, "2026-07-20")
        self.store.record(BreakOutcome.AWAY, "2026-07-20")
        self.assertEqual(
            self.store.load("2026-07-20"), DailyStats(taken=1, away=2)
        )

    def test_missed_breaks_are_counted_apart_from_taken_breaks(self):
        self.store.record(BreakOutcome.TAKEN, "2026-07-20")
        self.store.record(BreakOutcome.MISSED, "2026-07-20")
        self.assertEqual(
            self.store.load("2026-07-20"), DailyStats(taken=1, missed=1)
        )

    def test_each_day_is_counted_separately(self):
        self.store.record(BreakOutcome.TAKEN, "2026-07-19")
        self.store.record(BreakOutcome.SNOOZED, "2026-07-20")
        self.assertEqual(self.store.load("2026-07-19"), DailyStats(taken=1))
        self.assertEqual(self.store.load("2026-07-20"), DailyStats(snoozed=1))

    def test_history_is_trimmed_to_a_bounded_window(self):
        for day in range(1, HISTORY_DAYS + 12):
            self.store.record(BreakOutcome.TAKEN, f"2026-{day // 28 + 1:02d}-{day % 28 + 1:02d}")
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertLessEqual(len(stored["days"]), HISTORY_DAYS)

    def test_malformed_file_does_not_crash_and_recovers_on_write(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(self.store.load("2026-07-20"), DailyStats())

        self.store.record(BreakOutcome.TAKEN, "2026-07-20")
        self.assertEqual(self.store.load("2026-07-20"), DailyStats(taken=1))

    def test_each_outcome_is_recorded_with_its_time_of_day(self):
        self.store.record(BreakOutcome.TAKEN, "2026-07-20", at="09:30")
        self.store.record(BreakOutcome.MISSED, "2026-07-20", at="14:05")
        self.assertEqual(
            self.store.load_events("2026-07-20"),
            [(9 * 60 + 30, "taken"), (14 * 60 + 5, "missed")],
        )
        self.assertEqual(
            self.store.load("2026-07-20"), DailyStats(taken=1, missed=1)
        )

    def test_old_event_lists_are_dropped_but_their_counters_stay(self):
        self.store.record(BreakOutcome.TAKEN, "2026-07-01", at="09:30")
        self.store.record(BreakOutcome.TAKEN, "2026-07-20", at="10:00")
        self.assertEqual(self.store.load_events("2026-07-01"), [])
        self.assertEqual(self.store.load("2026-07-01"), DailyStats(taken=1))
        self.assertEqual(
            self.store.load_events("2026-07-20"), [(10 * 60, "taken")]
        )

    def test_a_day_without_events_has_an_empty_timeline(self):
        self.assertEqual(self.store.load_events("2026-07-20"), [])

    def test_malformed_events_are_skipped(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "days": {
                        "2026-07-20": {
                            "taken": 2,
                            "events": [
                                ["09:30", "taken"],
                                ["bogus", "taken"],
                                "not-a-pair",
                                ["10:15", 7],
                                ["26:70", "taken"],
                                ["-1:30", "taken"],
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            self.store.load_events("2026-07-20"), [(9 * 60 + 30, "taken")]
        )

    def test_load_days_reads_several_days_at_once(self):
        self.store.record(BreakOutcome.TAKEN, "2026-07-19")
        self.store.record(BreakOutcome.MISSED, "2026-07-21")
        self.assertEqual(
            self.store.load_days(["2026-07-19", "2026-07-20", "2026-07-21"]),
            [DailyStats(taken=1), DailyStats(), DailyStats(missed=1)],
        )

    def test_unreadable_location_does_not_raise(self):
        store = StatsStore(Path(self.temp_dir.name) / "file.txt" / "stats.json")
        Path(self.temp_dir.name, "file.txt").write_text("blocker", encoding="utf-8")
        store.record(BreakOutcome.TAKEN, "2026-07-20")
        self.assertEqual(store.load("2026-07-20"), DailyStats())

    def test_negative_or_garbage_counters_are_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"days": {"2026-07-20": {"taken": -3, "skipped": "lots"}}}),
            encoding="utf-8",
        )
        self.assertEqual(self.store.load("2026-07-20"), DailyStats())


if __name__ == "__main__":
    unittest.main()
