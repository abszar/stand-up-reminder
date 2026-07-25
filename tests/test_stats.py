import json
import tempfile
import unittest
from pathlib import Path

from stand_up_reminder.stats import (
    HISTORY_DAYS,
    BreakOutcome,
    DailyStats,
    StatsStore,
    adherence_percent,
    aggregate_stats,
    last_days,
    rating_label,
    score_line,
    summary_label,
    week_label,
)


class SummaryLabelTests(unittest.TestCase):
    def test_reports_a_quiet_day(self):
        self.assertEqual(summary_label(DailyStats()), "No breaks yet today")

    def test_reports_only_the_outcomes_that_happened(self):
        self.assertEqual(
            summary_label(DailyStats(taken=1)), "Today: 1 break taken"
        )
        self.assertEqual(
            summary_label(DailyStats(taken=4, skipped=2)),
            "Today: 4 breaks taken, 2 skipped",
        )

    def test_reports_every_outcome(self):
        self.assertEqual(
            summary_label(
                DailyStats(taken=3, away=2, missed=4, skipped=1, snoozed=5)
            ),
            "Today: 3 breaks taken, 2 away, 4 missed, 1 skipped, 5 snoozed",
        )

    def test_reports_a_day_with_only_missed_breaks(self):
        self.assertEqual(summary_label(DailyStats(missed=2)), "Today: 2 missed")

    def test_reports_a_day_with_only_away_credits(self):
        self.assertEqual(summary_label(DailyStats(away=4)), "Today: 4 away")


class WeekLabelTests(unittest.TestCase):
    def test_reports_a_quiet_week(self):
        self.assertEqual(week_label(DailyStats()), "No breaks this week")

    def test_reports_the_week_outcomes(self):
        self.assertEqual(
            week_label(DailyStats(taken=12, missed=3)),
            "This week: 12 breaks taken, 3 missed",
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
        self.assertEqual(rating_label(None), "No breaks due yet")
        self.assertEqual(rating_label(100), "Excellent — you rarely miss a break")
        self.assertEqual(rating_label(90), "Excellent — you rarely miss a break")
        self.assertEqual(rating_label(70), "Good — most breaks taken")
        self.assertEqual(rating_label(40), "Could be better — many breaks slip by")
        self.assertEqual(rating_label(39), "Time to stand up more often")


class ScoreLineTests(unittest.TestCase):
    def test_shows_both_scores_with_their_mood(self):
        self.assertEqual(
            score_line(75, 92), "Today: 75% 🙂 · This week: 92% 😄"
        )
        self.assertEqual(
            score_line(40, 20), "Today: 40% 😐 · This week: 20% 😟"
        )

    def test_shows_a_dash_when_no_breaks_were_due(self):
        self.assertEqual(score_line(None, None), "Today: — · This week: —")
        self.assertEqual(score_line(None, 100), "Today: — · This week: 100% 😄")


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
