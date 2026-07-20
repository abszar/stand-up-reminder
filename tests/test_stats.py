import json
import tempfile
import unittest
from pathlib import Path

from stand_up_reminder.stats import (
    HISTORY_DAYS,
    BreakOutcome,
    DailyStats,
    StatsStore,
    summary_label,
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
            summary_label(DailyStats(taken=3, skipped=1, snoozed=5)),
            "Today: 3 breaks taken, 1 skipped, 5 snoozed",
        )


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
