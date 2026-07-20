import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from stand_up_reminder import application

from stand_up_reminder.application import (
    break_progress_fraction,
    duration_label,
    format_duration,
    indicator_label,
    is_wayland_session,
)
from stand_up_reminder.scheduler import Phase
from stand_up_reminder.stats import DailyStats


class FormatDurationTests(unittest.TestCase):
    def test_formats_minutes_and_seconds(self):
        self.assertEqual(format_duration(120), "02:00")
        self.assertEqual(format_duration(61), "01:01")
        self.assertEqual(format_duration(0), "00:00")

    def test_clamps_negative_values(self):
        self.assertEqual(format_duration(-4), "00:00")


class DurationLabelTests(unittest.TestCase):
    def test_labels_whole_minutes(self):
        self.assertEqual(duration_label(60), "1 minute")
        self.assertEqual(duration_label(20 * 60), "20 minutes")

    def test_labels_whole_hours(self):
        self.assertEqual(duration_label(60 * 60), "1 hour")
        self.assertEqual(duration_label(2 * 60 * 60), "2 hours")

    def test_labels_mixed_hours_and_minutes(self):
        self.assertEqual(duration_label(90 * 60), "1 hour 30 minutes")

    def test_labels_sub_minute_durations_in_seconds(self):
        self.assertEqual(duration_label(30), "30 seconds")
        self.assertEqual(duration_label(1), "1 second")


class BreakProgressTests(unittest.TestCase):
    def test_reports_fraction_of_break_remaining(self):
        self.assertEqual(break_progress_fraction(120, 120), 1.0)
        self.assertEqual(break_progress_fraction(30, 120), 0.25)
        self.assertEqual(break_progress_fraction(0, 120), 0.0)

    def test_clamps_values_and_handles_invalid_total(self):
        self.assertEqual(break_progress_fraction(200, 120), 1.0)
        self.assertEqual(break_progress_fraction(-1, 120), 0.0)
        self.assertEqual(break_progress_fraction(10, 0), 0.0)


class WaylandDetectionTests(unittest.TestCase):
    def test_detects_a_wayland_session(self):
        self.assertTrue(is_wayland_session({"XDG_SESSION_TYPE": "wayland"}))

    def test_detects_an_x11_session(self):
        self.assertFalse(is_wayland_session({"XDG_SESSION_TYPE": "x11"}))

    def test_backend_override_wins(self):
        self.assertTrue(
            is_wayland_session({"XDG_SESSION_TYPE": "x11", "GDK_BACKEND": "wayland"})
        )
        self.assertFalse(
            is_wayland_session({"XDG_SESSION_TYPE": "wayland", "GDK_BACKEND": "x11"})
        )

    def test_unknown_session_is_treated_as_x11(self):
        self.assertFalse(is_wayland_session({}))


class IndicatorLabelTests(unittest.TestCase):
    def test_shows_the_work_countdown(self):
        self.assertEqual(indicator_label(Phase.WORK, 14 * 60 + 5, True), "14:05")

    def test_is_empty_when_the_countdown_is_disabled(self):
        self.assertEqual(indicator_label(Phase.WORK, 840, False), "")

    def test_is_empty_while_the_break_window_is_showing(self):
        self.assertEqual(indicator_label(Phase.BREAK, 60, True), "")
        self.assertEqual(indicator_label(Phase.AWAITING_RETURN, 0, True), "")

    def test_shows_the_snooze_countdown(self):
        self.assertEqual(indicator_label(Phase.SNOOZED, 65, True), "01:05")

    def test_marks_a_paused_timer(self):
        self.assertEqual(indicator_label(Phase.PAUSED, 0, True), "Paused")


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
        self.assertTrue(view.can_pause)
        self.assertFalse(view.can_resume)

    def test_snoozed_view(self):
        view = application.indicator_view(Phase.SNOOZED, 4 * 60 + 9, 0)
        self.assertEqual(view.status, "Break snoozed for 04:09")
        self.assertFalse(view.can_start_break)
        self.assertFalse(view.can_reset_work)
        self.assertFalse(view.can_pause)

    def test_active_break_view(self):
        view = application.indicator_view(Phase.BREAK, 75, 45)
        self.assertEqual(view.status, "Break in progress")
        self.assertFalse(view.can_start_break)
        self.assertFalse(view.can_reset_work)
        self.assertFalse(view.can_pause)

    def test_awaiting_return_view(self):
        view = application.indicator_view(Phase.AWAITING_RETURN, 0, 15 * 60)
        self.assertEqual(view.status, "Away for 15:00")
        self.assertFalse(view.can_start_break)
        self.assertTrue(view.can_reset_work)
        self.assertFalse(view.can_pause)

    def test_indefinite_pause_view(self):
        view = application.indicator_view(
            Phase.PAUSED, 0, 0, paused_indefinitely=True
        )
        self.assertEqual(view.status, "Reminders paused")
        self.assertFalse(view.can_start_break)
        self.assertFalse(view.can_pause)
        self.assertTrue(view.can_resume)

    def test_timed_pause_view_counts_down(self):
        view = application.indicator_view(Phase.PAUSED, 42 * 60, 0)
        self.assertEqual(view.status, "Paused for 42:00")
        self.assertTrue(view.can_resume)


class StatsSummaryCacheTests(unittest.TestCase):
    """The interface refreshes four times a second, so the daily counters are
    read from disk only when they can actually have changed."""

    def make_coordinator(self, stored=None):
        stats = Mock()
        stats.load.return_value = stored or DailyStats(taken=2)
        return SimpleNamespace(
            stats=stats,
            _stats_day="2026-07-20",
            _stats_summary="Today: 2 breaks taken",
        )

    def test_summary_is_not_reloaded_within_the_same_day(self):
        coordinator = self.make_coordinator()

        application.ReminderApplication._stats_label(coordinator, "2026-07-20")

        coordinator.stats.load.assert_not_called()

    def test_summary_is_reloaded_when_the_day_rolls_over(self):
        coordinator = self.make_coordinator(DailyStats())

        label = application.ReminderApplication._stats_label(
            coordinator, "2026-07-21"
        )

        coordinator.stats.load.assert_called_once_with("2026-07-21")
        self.assertEqual(label, "No breaks yet today")
        self.assertEqual(coordinator._stats_day, "2026-07-21")

    def test_recording_an_outcome_refreshes_the_summary(self):
        coordinator = self.make_coordinator(DailyStats(taken=3))

        application.ReminderApplication._record_outcome(
            coordinator, application.BreakOutcome.TAKEN
        )

        coordinator.stats.record.assert_called_once_with(
            application.BreakOutcome.TAKEN
        )
        self.assertEqual(coordinator._stats_summary, "Today: 3 breaks taken")

    def test_a_missing_stats_store_is_tolerated(self):
        coordinator = SimpleNamespace(
            stats=None, _stats_day="2026-07-20", _stats_summary="cached"
        )

        application.ReminderApplication._record_outcome(
            coordinator, application.BreakOutcome.TAKEN
        )

        self.assertEqual(coordinator._stats_summary, "cached")


class BreakActionCoordinatorTests(unittest.TestCase):
    def make_coordinator(self):
        return SimpleNamespace(
            scheduler=Mock(),
            window=Mock(),
            stats=Mock(),
            _update_interface=Mock(),
            _record_outcome=Mock(),
            _hide_dimmers=Mock(),
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

    def test_snooze_and_skip_are_counted_separately(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.snooze_break.return_value = True
        coordinator.scheduler.skip_break.return_value = True

        application.ReminderApplication._snooze_break(coordinator, None)
        application.ReminderApplication._skip_break(coordinator, None)

        recorded = [call.args[0] for call in coordinator._record_outcome.call_args_list]
        self.assertEqual(
            recorded,
            [application.BreakOutcome.SNOOZED, application.BreakOutcome.SKIPPED],
        )

    def test_rejected_actions_are_not_counted(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.snooze_break.return_value = False
        coordinator.scheduler.skip_break.return_value = False

        application.ReminderApplication._snooze_break(coordinator, None)
        application.ReminderApplication._skip_break(coordinator, None)

        coordinator._record_outcome.assert_not_called()


if __name__ == "__main__":
    unittest.main()
