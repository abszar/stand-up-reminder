import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from stand_up_reminder import application

from stand_up_reminder.application import (
    break_progress_fraction,
    duration_label,
    format_duration,
    heat_cell_at,
    heat_cell_size,
    heat_grid_height,
    hex_rgb,
    idle_credit_threshold,
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


class HeatGeometryTests(unittest.TestCase):
    """The grid fills the width it is given, with square days."""

    def test_cells_divide_the_width_left_after_labels_and_gaps(self):
        cell = heat_cell_size(500, 12, gap=4, label_width=38)
        self.assertAlmostEqual(cell, (500 - 38 - 11 * 4) / 12)

    def test_a_narrow_or_empty_grid_never_goes_negative(self):
        self.assertEqual(heat_cell_size(20, 12), 0.0)
        self.assertEqual(heat_cell_size(500, 0), 0.0)

    def test_height_follows_the_seven_weekday_rows(self):
        self.assertEqual(
            heat_grid_height(30, gap=4, month_height=18), 18 + 7 * 30 + 6 * 4
        )

    def test_a_point_maps_to_the_day_square_under_it(self):
        # 12 columns of 30px squares, 4px apart, after a 38px label column.
        geometry = dict(columns=12, cell=30, gap=4, label_width=38, month_height=18)
        self.assertEqual(heat_cell_at(40, 20, **geometry), (0, 0))
        self.assertEqual(heat_cell_at(38 + 34 + 5, 18 + 34 + 5, **geometry), (1, 1))

    def test_labels_gaps_and_the_outside_map_to_nothing(self):
        geometry = dict(columns=12, cell=30, gap=4, label_width=38, month_height=18)
        self.assertIsNone(heat_cell_at(10, 40, **geometry))
        self.assertIsNone(heat_cell_at(40, 5, **geometry))
        self.assertIsNone(heat_cell_at(38 + 31, 20, **geometry))
        self.assertIsNone(heat_cell_at(4000, 20, **geometry))
        self.assertIsNone(heat_cell_at(40, 4000, **geometry))


class CountdownColorTests(unittest.TestCase):
    """The warning countdown starts white and turns red as it runs out."""

    def test_starts_white_and_ends_red(self):
        self.assertEqual(application.countdown_color(10, 10), "#f7f2e7")
        self.assertEqual(application.countdown_color(0, 10), "#e05d5d")

    def test_passes_through_the_two_colors_on_the_way(self):
        middle = application.countdown_color(5, 10)
        red, green, blue = application.hex_rgb(middle)
        self.assertTrue(0xE0 / 255 < red < 0xF7 / 255)
        self.assertTrue(0x5D / 255 < green < 0xF2 / 255)
        self.assertTrue(0x5D / 255 < blue < 0xE7 / 255)

    def test_clamps_beyond_the_warning_window(self):
        self.assertEqual(application.countdown_color(40, 10), "#f7f2e7")
        self.assertEqual(application.countdown_color(-5, 10), "#e05d5d")
        self.assertEqual(application.countdown_color(5, 0), "#e05d5d")


class HexRgbTests(unittest.TestCase):
    def test_converts_hex_colors_to_unit_floats(self):
        self.assertEqual(hex_rgb("#ff0000"), (1.0, 0.0, 0.0))
        self.assertEqual(hex_rgb("#000000"), (0.0, 0.0, 0.0))
        red, green, blue = hex_rgb("#7bc47f")
        self.assertAlmostEqual(red, 0x7B / 255)
        self.assertAlmostEqual(green, 0xC4 / 255)
        self.assertAlmostEqual(blue, 0x7F / 255)


class IdleCreditThresholdTests(unittest.TestCase):
    def test_uses_the_configured_idle_threshold(self):
        self.assertEqual(idle_credit_threshold(10 * 60, 2 * 60), 10 * 60)

    def test_never_drops_below_the_break_length(self):
        self.assertEqual(idle_credit_threshold(5 * 60, 10 * 60), 10 * 60)


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
        self.assertTrue(view.can_miss)

    def test_active_break_cannot_be_declared_missed(self):
        view = application.break_view(Phase.BREAK, 75, 45)
        self.assertFalse(view.can_miss)

    def test_work_phase_shows_the_pre_break_warning(self):
        view = application.break_view(Phase.WORK, 15, 0)
        self.assertEqual(view.title, "Break coming up")
        self.assertEqual(view.countdown, "00:15")
        self.assertEqual(view.away, "Time to stand up in 00:15")
        self.assertFalse(view.can_return)
        self.assertFalse(view.can_miss)

    def test_the_warning_offers_the_same_break_actions(self):
        view = application.break_view(Phase.WORK, 15, 0)
        self.assertTrue(view.can_snooze)
        self.assertTrue(view.can_skip)

    def test_snoozed_view_has_no_popup_actions(self):
        view = application.break_view(Phase.SNOOZED, 5 * 60, 0)
        self.assertFalse(view.can_snooze)
        self.assertFalse(view.can_skip)
        self.assertFalse(view.can_return)
        self.assertFalse(view.can_miss)


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
            stats_window=None,
            _stats_day="2026-07-20",
            _stats_summary="Today: 2 breaks taken",
            _refresh_score_line=Mock(),
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
