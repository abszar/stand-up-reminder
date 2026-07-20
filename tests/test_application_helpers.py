import unittest

from stand_up_reminder import application

from stand_up_reminder.application import break_progress_fraction, format_duration
from stand_up_reminder.scheduler import Phase


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


class BreakViewTests(unittest.TestCase):
    def test_minimum_break_view(self):
        view = application.break_view(Phase.BREAK, 75, 45)
        self.assertEqual(view.title, "Time to stand up")
        self.assertEqual(view.countdown, "01:15")
        self.assertEqual(view.away, "Away for 00:45")
        self.assertFalse(view.can_return)

    def test_awaiting_return_view(self):
        view = application.break_view(Phase.AWAITING_RETURN, 0, 15 * 60)
        self.assertEqual(view.title, "Break complete")
        self.assertEqual(view.countdown, "00:00")
        self.assertEqual(view.away, "Away for 15:00")
        self.assertTrue(view.can_return)

if __name__ == "__main__":
    unittest.main()
