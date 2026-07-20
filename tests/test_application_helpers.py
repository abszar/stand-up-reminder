import unittest

from stand_up_reminder.application import break_progress_fraction, format_duration


class FormatDurationTests(unittest.TestCase):
    def test_formats_minutes_and_seconds(self):
        self.assertEqual(format_duration(120), "02:00")
        self.assertEqual(format_duration(61), "01:01")
        self.assertEqual(format_duration(0), "00:00")

    def test_clamps_negative_values(self):
        self.assertEqual(format_duration(-4), "00:00")


class BreakProgressTests(unittest.TestCase):
    def test_reports_fraction_of_break_remaining(self):
        self.assertEqual(break_progress_fraction(120, 120), 1.0)
        self.assertEqual(break_progress_fraction(30, 120), 0.25)
        self.assertEqual(break_progress_fraction(0, 120), 0.0)

    def test_clamps_values_and_handles_invalid_total(self):
        self.assertEqual(break_progress_fraction(200, 120), 1.0)
        self.assertEqual(break_progress_fraction(-1, 120), 0.0)
        self.assertEqual(break_progress_fraction(10, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
