import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from stand_up_reminder import application

from stand_up_reminder.application import (
    duration_label,
    format_duration,
    idle_credit_threshold,
    indicator_label,
    is_wayland_session,
    menu_blocks,
    short_minutes,
)
from stand_up_reminder.pixels import PALETTE
from stand_up_reminder.scheduler import Phase, Transition
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



class PillPositionTests(unittest.TestCase):
    def test_places_the_pill_by_fraction_of_the_screen(self):
        self.assertEqual(application.pill_position(0.5, 1000, 40), 480)
        self.assertEqual(application.pill_position(0.0, 1000, 40), 0)

    def test_keeps_the_whole_pill_on_screen(self):
        self.assertEqual(application.pill_position(1.0, 1000, 40), 960)
        self.assertEqual(application.pill_position(-1.0, 1000, 40), 0)

    def test_a_pill_taller_than_the_screen_starts_at_the_top(self):
        self.assertEqual(application.pill_position(0.8, 30, 40), 0)

    def test_fraction_round_trips_through_a_position(self):
        self.assertAlmostEqual(application.pill_fraction(480, 1000, 40), 0.5)
        self.assertEqual(application.pill_fraction(-20, 1000, 40), 0.0)
        self.assertEqual(application.pill_fraction(5_000, 1000, 40), 1.0)

    def test_fraction_of_a_screen_shorter_than_the_pill_is_the_top(self):
        self.assertEqual(application.pill_fraction(10, 30, 40), 0.0)


class CountdownStateTests(unittest.TestCase):
    def test_the_clock_reddens_in_the_last_ten_seconds(self):
        self.assertTrue(application.is_urgent(10))
        self.assertFalse(application.is_urgent(11))
        self.assertEqual(
            application.countdown_color(10, True), PALETTE["coral"]
        )
        self.assertEqual(
            application.countdown_color(30, False), PALETTE["bone"]
        )

    def test_the_shudder_tightens_under_five_seconds(self):
        self.assertIsNone(application.shudder_period(11))
        self.assertEqual(application.shudder_period(10), 120)
        self.assertEqual(application.shudder_period(5), 80)


class MenuBlockTests(unittest.TestCase):
    def test_kept_breaks_are_filled_and_lost_ones_hollow(self):
        self.assertEqual(
            menu_blocks(DailyStats(taken=2, away=1, missed=1)), "▮▮▮▯"
        )

    def test_a_quiet_day_has_no_blocks(self):
        self.assertEqual(menu_blocks(DailyStats()), "")

    def test_a_long_day_is_scaled_to_the_cap(self):
        blocks = menu_blocks(DailyStats(taken=9, missed=3), cap=8)
        self.assertEqual(len(blocks), 8)
        self.assertEqual(blocks.count("▮"), 6)


class ShortMinutesTests(unittest.TestCase):
    def test_rounds_to_whole_minutes_for_the_button_labels(self):
        self.assertEqual(short_minutes(5 * 60), 5)
        self.assertEqual(short_minutes(90), 2)

    def test_never_reads_as_zero(self):
        self.assertEqual(short_minutes(5), 1)


class BreakViewTests(unittest.TestCase):
    def test_minimum_break_view(self):
        view = application.break_view(Phase.BREAK, 75, 45)
        self.assertEqual(view.title, "Up you get")
        self.assertEqual(view.countdown, "01:15")
        self.assertEqual(view.secondary, "Up for 00:45")
        self.assertTrue(view.can_snooze)
        self.assertTrue(view.can_skip)
        self.assertFalse(view.can_return)
        self.assertTrue(view.can_stand)

    def test_awaiting_return_view(self):
        view = application.break_view(Phase.AWAITING_RETURN, 0, 15 * 60)
        self.assertEqual(view.title, "Nice one")
        self.assertEqual(view.countdown, "00:00")
        self.assertEqual(view.secondary, "Up for 15:00")
        self.assertEqual(view.title_color, PALETTE["mint"])
        self.assertFalse(view.can_snooze)
        self.assertFalse(view.can_skip)
        self.assertTrue(view.can_return)
        self.assertTrue(view.can_stand)
        self.assertTrue(view.can_miss)

    def test_active_break_cannot_be_declared_missed(self):
        view = application.break_view(Phase.BREAK, 75, 45)
        self.assertFalse(view.can_miss)

    def test_work_phase_shows_the_pre_break_warning(self):
        view = application.break_view(Phase.WORK, 15, 0)
        self.assertEqual(view.title, "Break coming up")
        self.assertEqual(view.countdown, "00:15")
        self.assertEqual(view.secondary, "Standing up in 00:15")
        self.assertFalse(view.can_return)
        self.assertFalse(view.can_stand)
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
        self.assertFalse(view.can_stand)


class StandingActionTests(unittest.TestCase):
    def test_the_row_offers_to_stand_when_seated(self):
        self.assertEqual(application.standing_action_label(False), "I'm standing now")

    def test_the_row_offers_to_sit_when_standing(self):
        self.assertEqual(application.standing_action_label(True), "I'm sitting down")


class BreakHintTests(unittest.TestCase):
    def test_the_break_names_all_three_keys(self):
        view = application.break_view(Phase.BREAK, 75, 45)
        self.assertEqual(application.break_hint(view), "S SNOOZE · K SKIP · T STANDING")

    def test_the_warning_has_no_standing_key(self):
        view = application.break_view(Phase.WORK, 15, 0)
        self.assertEqual(application.break_hint(view), "S SNOOZE · K SKIP")

    def test_a_finished_break_confirms_or_stands(self):
        view = application.break_view(Phase.AWAITING_RETURN, 0, 90)
        self.assertEqual(application.break_hint(view), "ENTER · T STANDING")


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
        self.assertEqual(view.status, "Up for 15:00")
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
        self.assertEqual(label, "Nothing recorded yet")
        self.assertEqual(coordinator._stats_day, "2026-07-21")

    def test_recording_an_outcome_refreshes_the_summary(self):
        coordinator = self.make_coordinator(DailyStats(taken=3))

        application.ReminderApplication._record_outcome(
            coordinator, application.BreakOutcome.TAKEN
        )

        coordinator.stats.record.assert_called_once_with(
            application.BreakOutcome.TAKEN
        )
        self.assertEqual(coordinator._stats_summary, "▮▮▮  3 taken")

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


class StandingCoordinatorTests(unittest.TestCase):
    def make_coordinator(self):
        return SimpleNamespace(
            scheduler=Mock(),
            window=Mock(),
            stats=Mock(),
            pill=Mock(),
            _standing_since=None,
            _update_interface=Mock(),
            _record_outcome=Mock(),
            _apply_transition=Mock(),
            _start_standing=Mock(),
        )

    def test_standing_counts_the_break_as_taken_and_opens_the_pill(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.stand_up.return_value = Transition.END_BREAK

        application.ReminderApplication._stand_up(coordinator, None)

        coordinator._record_outcome.assert_called_once_with(
            application.BreakOutcome.TAKEN
        )
        coordinator._apply_transition.assert_called_once_with(Transition.END_BREAK)
        coordinator._update_interface.assert_called_once_with()

    def test_the_pill_carries_on_from_the_break_s_own_clock(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.stand_up.return_value = Transition.END_BREAK
        coordinator.scheduler.snapshot.return_value = SimpleNamespace(
            away_seconds=45
        )

        application.ReminderApplication._stand_up(coordinator, None)

        coordinator._start_standing.assert_called_once_with(45)

    def test_standing_from_a_fresh_break_starts_at_zero(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.stand_up.return_value = Transition.END_BREAK
        coordinator.scheduler.snapshot.return_value = SimpleNamespace(
            away_seconds=0
        )

        application.ReminderApplication._stand_up(coordinator, None)

        coordinator._start_standing.assert_called_once_with(0)

    def test_standing_outside_a_break_changes_nothing(self):
        coordinator = self.make_coordinator()
        coordinator.scheduler.stand_up.return_value = None

        application.ReminderApplication._stand_up(coordinator, None)

        coordinator._record_outcome.assert_not_called()
        coordinator._start_standing.assert_not_called()
        coordinator._update_interface.assert_called_once_with()

    def test_sitting_down_hides_the_pill_and_forgets_the_start(self):
        coordinator = self.make_coordinator()
        coordinator._standing_since = 100.0

        application.ReminderApplication._stop_standing(coordinator)

        coordinator.pill.hide.assert_called_once_with()
        self.assertIsNone(coordinator._standing_since)

    def test_sitting_down_restarts_the_work_interval(self):
        coordinator = self.make_coordinator()
        coordinator._standing_since = 100.0

        application.ReminderApplication._stop_standing(coordinator)

        coordinator.scheduler.set_standing.assert_called_once_with(False)
        coordinator.scheduler.reset_work_interval.assert_called_once_with()

    def test_the_pill_holds_the_work_interval_while_it_counts(self):
        coordinator = SimpleNamespace(
            pill=Mock(), _standing_since=None, _clock=lambda: 500.0,
            scheduler=Mock(),
            settings=SimpleNamespace(standing_pill_position=0.5),
        )

        application.ReminderApplication._start_standing(coordinator)

        coordinator.scheduler.set_standing.assert_called_once_with(True)

    def test_standing_from_the_menu_starts_the_counter(self):
        coordinator = self.make_coordinator()
        coordinator._standing_since = None
        coordinator._stop_standing = Mock()

        application.ReminderApplication._toggle_standing(coordinator, None)

        coordinator._start_standing.assert_called_once_with()
        coordinator._stop_standing.assert_not_called()

    def test_the_same_row_sits_back_down(self):
        coordinator = self.make_coordinator()
        coordinator._standing_since = 100.0
        coordinator._stop_standing = Mock()

        application.ReminderApplication._toggle_standing(coordinator, None)

        coordinator._stop_standing.assert_called_once_with()
        coordinator._start_standing.assert_not_called()

    def test_standing_from_the_menu_leaves_the_timers_alone(self):
        coordinator = self.make_coordinator()
        coordinator._standing_since = None
        coordinator._stop_standing = Mock()

        application.ReminderApplication._toggle_standing(coordinator, None)

        coordinator.scheduler.stand_up.assert_not_called()
        coordinator._record_outcome.assert_not_called()

    def test_a_break_answered_while_already_up_keeps_the_count(self):
        coordinator = SimpleNamespace(
            pill=Mock(), _standing_since=300.0, _clock=lambda: 900.0,
            scheduler=Mock(),
            settings=SimpleNamespace(standing_pill_position=0.5),
        )

        application.ReminderApplication._start_standing(coordinator, 45)

        self.assertEqual(coordinator._standing_since, 300.0)
        coordinator.pill.set_seconds.assert_called_once_with(600)

    def test_the_pill_opens_at_the_time_already_spent_up(self):
        coordinator = SimpleNamespace(
            pill=Mock(), _standing_since=None, _clock=lambda: 500.0,
            scheduler=Mock(),
            settings=SimpleNamespace(standing_pill_position=0.5),
        )

        application.ReminderApplication._start_standing(coordinator, 45)

        self.assertEqual(coordinator._standing_since, 455.0)
        coordinator.pill.set_seconds.assert_called_once_with(45)

    def test_the_pill_shows_the_time_since_standing_began(self):
        coordinator = SimpleNamespace(
            pill=Mock(), _standing_since=100.0, _clock=lambda: 175.4
        )

        application.ReminderApplication._refresh_standing_pill(coordinator)

        coordinator.pill.set_seconds.assert_called_once_with(75)

    def test_the_pill_is_left_alone_while_nobody_is_standing(self):
        coordinator = SimpleNamespace(
            pill=Mock(), _standing_since=None, _clock=lambda: 175.4
        )

        application.ReminderApplication._refresh_standing_pill(coordinator)

        coordinator.pill.set_seconds.assert_not_called()


if __name__ == "__main__":
    unittest.main()
