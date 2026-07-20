import unittest
from types import SimpleNamespace
from unittest.mock import Mock

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
        self.assertTrue(view.can_snooze)
        self.assertTrue(view.can_skip)
        self.assertFalse(view.can_return)

    def test_awaiting_return_view(self):
        view = application.break_view(Phase.AWAITING_RETURN, 0, 15 * 60)
        self.assertEqual(view.title, "Break complete")
        self.assertEqual(view.countdown, "00:00")
        self.assertEqual(view.away, "Away for 15:00")
        self.assertFalse(view.can_snooze)
        self.assertFalse(view.can_skip)
        self.assertTrue(view.can_return)

    def test_snoozed_view_has_no_popup_actions(self):
        view = application.break_view(Phase.SNOOZED, 5 * 60, 0)
        self.assertFalse(view.can_snooze)
        self.assertFalse(view.can_skip)
        self.assertFalse(view.can_return)


class IndicatorViewTests(unittest.TestCase):
    def test_work_view(self):
        view = application.indicator_view(Phase.WORK, 24 * 60, 0)
        self.assertEqual(view.status, "Next break in 24:00")
        self.assertTrue(view.can_start_break)
        self.assertTrue(view.can_reset_work)

    def test_snoozed_view(self):
        view = application.indicator_view(Phase.SNOOZED, 4 * 60 + 9, 0)
        self.assertEqual(view.status, "Break snoozed for 04:09")
        self.assertFalse(view.can_start_break)
        self.assertFalse(view.can_reset_work)

    def test_active_break_view(self):
        view = application.indicator_view(Phase.BREAK, 75, 45)
        self.assertEqual(view.status, "Break in progress")
        self.assertFalse(view.can_start_break)
        self.assertFalse(view.can_reset_work)

    def test_awaiting_return_view(self):
        view = application.indicator_view(
            Phase.AWAITING_RETURN, 0, 15 * 60
        )
        self.assertEqual(view.status, "Away for 15:00")
        self.assertFalse(view.can_start_break)
        self.assertTrue(view.can_reset_work)


class BreakActionCoordinatorTests(unittest.TestCase):
    def make_coordinator(self):
        return SimpleNamespace(
            scheduler=Mock(),
            window=Mock(),
            _update_interface=Mock(),
        )

    def test_successful_snooze_hides_popup_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.snooze_break.return_value = True

        application.ReminderApplication._snooze_break(coordinator, None)

        coordinator.window.hide.assert_called_once_with()
        coordinator._update_interface.assert_called_once_with()

    def test_rejected_snooze_keeps_popup_visible_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.snooze_break.return_value = False

        application.ReminderApplication._snooze_break(coordinator, None)

        coordinator.window.hide.assert_not_called()
        coordinator._update_interface.assert_called_once_with()

    def test_successful_skip_hides_popup_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.skip_break.return_value = True

        application.ReminderApplication._skip_break(coordinator, None)

        coordinator.window.hide.assert_called_once_with()
        coordinator._update_interface.assert_called_once_with()

    def test_rejected_skip_keeps_popup_visible_and_refreshes(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.skip_break.return_value = False

        application.ReminderApplication._skip_break(coordinator, None)

        coordinator.window.hide.assert_not_called()
        coordinator._update_interface.assert_called_once_with()

if __name__ == "__main__":
    unittest.main()
