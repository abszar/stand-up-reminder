import unittest

from stand_up_reminder.scheduler import Phase, Scheduler, TimingMode, Transition


class FakeClocks:
    def __init__(self):
        self.mono = 100.0
        self.wall = 1_000.0

    def monotonic(self):
        return self.mono

    def wall_clock(self):
        return self.wall

    def advance(self, seconds, *, suspended=False):
        self.wall += seconds
        if not suspended:
            self.mono += seconds


class SchedulerFixture(unittest.TestCase):
    def setUp(self):
        self.clocks = FakeClocks()
        self.scheduler = Scheduler(
            work_seconds=30,
            break_seconds=2,
            snooze_seconds=5,
            mode=TimingMode.ACTIVE,
            monotonic=self.clocks.monotonic,
            wall_clock=self.clocks.wall_clock,
        )


class SchedulerTests(SchedulerFixture):
    def test_initial_work_interval(self):
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 30)

    def test_work_deadline_starts_break(self):
        self.clocks.advance(30)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 2)

    def test_break_completion_waits_for_explicit_return(self):
        self.scheduler.start_break()
        self.clocks.advance(2)
        transition = self.scheduler.advance()
        snapshot = self.scheduler.snapshot()
        self.assertEqual(transition, Transition.BREAK_COMPLETE)
        self.assertEqual(snapshot.phase, Phase.AWAITING_RETURN)
        self.assertEqual(snapshot.seconds_remaining, 0)
        self.assertEqual(snapshot.away_seconds, 2)

    def test_snooze_reopens_a_fresh_break_after_wall_clock_delay(self):
        self.scheduler.start_break()

        self.assertTrue(self.scheduler.snooze_break())
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.SNOOZED)
        self.assertEqual(snapshot.seconds_remaining, 5)
        self.assertEqual(snapshot.away_seconds, 0)

        self.clocks.advance(4, suspended=True)
        self.assertIsNone(self.scheduler.advance())
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 1)

        self.clocks.advance(1, suspended=True)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.BREAK)
        self.assertEqual(snapshot.seconds_remaining, 2)
        self.assertEqual(snapshot.away_seconds, 0)

    def test_break_can_be_snoozed_repeatedly(self):
        self.scheduler.start_break()
        self.assertTrue(self.scheduler.snooze_break())
        self.clocks.advance(5)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)

        self.assertTrue(self.scheduler.snooze_break())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.SNOOZED)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 5)

    def test_overdue_snooze_starts_break_on_unlock(self):
        self.scheduler.start_break()
        self.scheduler.snooze_break()
        self.scheduler.set_locked(True)

        self.clocks.advance(7, suspended=True)
        self.assertEqual(
            self.scheduler.set_locked(False), Transition.START_BREAK
        )
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.BREAK)
        self.assertEqual(snapshot.seconds_remaining, 2)
        self.assertFalse(snapshot.locked)

    def test_skip_break_starts_full_work_interval_at_click_time(self):
        self.scheduler.start_break()
        self.clocks.advance(1)

        self.assertTrue(self.scheduler.skip_break())
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 30)
        self.assertEqual(snapshot.away_seconds, 0)

        self.clocks.advance(6)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 24)

    def test_snooze_and_skip_are_rejected_outside_active_break(self):
        self.assertFalse(self.scheduler.snooze_break())
        self.assertFalse(self.scheduler.skip_break())

        self.scheduler.start_break()
        self.assertTrue(self.scheduler.snooze_break())
        self.assertFalse(self.scheduler.snooze_break())
        self.assertFalse(self.scheduler.skip_break())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.SNOOZED)

    def test_snooze_at_break_deadline_cannot_bypass_return(self):
        self.scheduler.start_break()
        self.clocks.advance(2)

        self.assertFalse(self.scheduler.snooze_break())
        self.assertEqual(
            self.scheduler.snapshot().phase, Phase.AWAITING_RETURN
        )

    def test_skip_at_break_deadline_cannot_bypass_return(self):
        self.scheduler.start_break()
        self.clocks.advance(2)

        self.assertFalse(self.scheduler.skip_break())
        self.assertEqual(
            self.scheduler.snapshot().phase, Phase.AWAITING_RETURN
        )

    def test_work_reset_cannot_bypass_snoozed_break(self):
        self.scheduler.start_break()
        self.scheduler.snooze_break()

        self.assertFalse(self.scheduler.reset_work_interval())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.SNOOZED)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 5)

    def test_return_confirmation_is_rejected_during_minimum(self):
        self.scheduler.start_break()
        self.clocks.advance(1)
        self.assertIsNone(self.scheduler.confirm_return())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)

    def test_return_confirmation_starts_full_interval_at_click_time(self):
        self.scheduler.start_break()
        self.clocks.advance(7)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.confirm_return(), Transition.END_BREAK)
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 30)
        self.assertEqual(snapshot.away_seconds, 0)
        self.clocks.advance(6)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 24)

    def test_work_reset_confirms_return_after_minimum(self):
        self.scheduler.start_break()
        self.clocks.advance(2)
        self.scheduler.advance()
        self.assertTrue(self.scheduler.reset_work_interval())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_manual_start_is_ignored_while_awaiting_return(self):
        self.scheduler.start_break()
        self.clocks.advance(2)
        self.scheduler.advance()
        self.assertIsNone(self.scheduler.start_break())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.AWAITING_RETURN)

    def test_away_time_continues_while_awaiting_return(self):
        self.scheduler.start_break()
        self.clocks.advance(2)
        self.scheduler.advance()
        self.clocks.advance(13, suspended=True)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().away_seconds, 15)

    def test_manual_start_is_ignored_during_break(self):
        self.assertEqual(self.scheduler.start_break(), Transition.START_BREAK)
        self.assertIsNone(self.scheduler.start_break())

    def test_manual_start_preserves_automatic_deadline_transition(self):
        self.clocks.advance(30)
        self.assertEqual(self.scheduler.start_break(), Transition.START_BREAK)

    def test_active_mode_pauses_during_lock(self):
        self.clocks.advance(10)
        self.scheduler.set_locked(True)
        self.clocks.advance(40)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 20)
        self.assertIsNone(self.scheduler.set_locked(False))

    def test_active_mode_excludes_suspend(self):
        self.clocks.advance(40, suspended=True)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_wall_mode_counts_lock_and_starts_on_unlock(self):
        self.scheduler.set_mode(TimingMode.WALL)
        self.scheduler.set_locked(True)
        self.clocks.advance(31)
        self.assertIsNone(self.scheduler.advance())
        self.assertEqual(self.scheduler.set_locked(False), Transition.START_BREAK)

    def test_wall_mode_counts_suspend(self):
        self.scheduler.set_mode(TimingMode.WALL)
        self.clocks.advance(31, suspended=True)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)

    def test_break_counts_lock_and_suspend_for_both_modes(self):
        self.scheduler.set_mode(TimingMode.WALL)
        self.scheduler.start_break()
        self.scheduler.set_locked(True)
        self.clocks.advance(5, suspended=True)
        self.assertEqual(self.scheduler.advance(), Transition.BREAK_COMPLETE)
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.AWAITING_RETURN)
        self.assertEqual(snapshot.seconds_remaining, 0)

    def test_snapshot_reports_away_time_from_break_start(self):
        self.scheduler.start_break()
        self.clocks.advance(1)
        self.scheduler.advance()
        snapshot = self.scheduler.snapshot()
        self.assertTrue(hasattr(snapshot, "away_seconds"))
        self.assertEqual(snapshot.away_seconds, 1)

    def test_policy_change_preserves_remaining_time(self):
        self.clocks.advance(7)
        self.scheduler.set_mode(TimingMode.WALL)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 23)

    def test_policy_change_reports_break_started_at_deadline(self):
        self.clocks.advance(30)
        self.assertEqual(
            self.scheduler.set_mode(TimingMode.WALL), Transition.START_BREAK
        )

    def test_long_break_return_resets_partial_work_interval(self):
        self.clocks.advance(11)
        self.assertTrue(self.scheduler.reset_work_interval())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_repeated_long_break_return_resets_are_full_intervals(self):
        self.clocks.advance(8)
        self.scheduler.reset_work_interval()
        self.clocks.advance(6)
        self.assertTrue(self.scheduler.reset_work_interval())
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_long_break_return_cannot_dismiss_active_break(self):
        self.scheduler.start_break()
        self.clocks.advance(1)
        self.assertFalse(self.scheduler.reset_work_interval())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 1)

    def test_long_break_return_at_deadline_preserves_enforced_break(self):
        self.clocks.advance(30)
        self.assertFalse(self.scheduler.reset_work_interval())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)


class PauseTests(SchedulerFixture):
    def test_indefinite_pause_holds_the_work_interval(self):
        self.clocks.advance(10)
        self.assertTrue(self.scheduler.pause())
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.PAUSED)
        self.assertTrue(snapshot.paused_indefinitely)

        self.clocks.advance(600)
        self.assertIsNone(self.scheduler.advance())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.PAUSED)

    def test_resume_restores_the_remaining_work_time(self):
        self.clocks.advance(10)
        self.scheduler.pause()
        self.clocks.advance(600)
        self.scheduler.resume()

        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 20)

    def test_timed_pause_resumes_work_on_its_own(self):
        self.clocks.advance(10)
        self.assertTrue(self.scheduler.pause(60))
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 60)
        self.assertFalse(self.scheduler.snapshot().paused_indefinitely)

        self.clocks.advance(60)
        self.assertIsNone(self.scheduler.advance())
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 20)

    def test_timed_pause_counts_wall_clock_across_suspend(self):
        self.scheduler.pause(60)
        self.clocks.advance(60, suspended=True)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)

    def test_pause_cannot_dismiss_an_active_break(self):
        self.scheduler.start_break()
        self.assertFalse(self.scheduler.pause())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)

    def test_pause_cannot_bypass_a_snoozed_break(self):
        self.scheduler.start_break()
        self.scheduler.snooze_break()
        self.assertFalse(self.scheduler.pause())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.SNOOZED)

    def test_pause_at_the_work_deadline_starts_the_break_instead(self):
        self.clocks.advance(30)
        self.assertFalse(self.scheduler.pause())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)

    def test_resume_is_ignored_when_not_paused(self):
        self.assertFalse(self.scheduler.resume())
        self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)


class DurationChangeTests(SchedulerFixture):
    def test_a_new_work_length_restarts_the_current_interval(self):
        self.clocks.advance(10)
        self.scheduler.set_durations(work_seconds=60)
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 60)

    def test_an_unchanged_work_length_leaves_the_interval_running(self):
        self.clocks.advance(10)
        self.scheduler.set_durations(break_seconds=30)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 20)

    def test_a_new_break_length_applies_to_the_next_break(self):
        self.scheduler.set_durations(break_seconds=30)
        self.scheduler.start_break()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_an_active_break_keeps_its_original_length(self):
        self.scheduler.start_break()
        self.scheduler.set_durations(break_seconds=600)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 2)

    def test_a_new_snooze_length_applies_to_the_next_snooze(self):
        self.scheduler.set_durations(snooze_seconds=90)
        self.scheduler.start_break()
        self.scheduler.snooze_break()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 90)

    def test_changing_the_work_length_re_arms_the_warning(self):
        self.scheduler.set_durations(work_seconds=30, warning_seconds=10)
        self.clocks.advance(20)
        self.assertEqual(self.scheduler.advance(), Transition.WARN_BREAK)

    def test_durations_can_be_changed_while_paused_without_resuming(self):
        self.scheduler.pause()
        self.scheduler.set_durations(work_seconds=60)
        self.assertEqual(self.scheduler.snapshot().phase, Phase.PAUSED)
        self.scheduler.resume()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 60)


class WarningTests(unittest.TestCase):
    def setUp(self):
        self.clocks = FakeClocks()
        self.scheduler = Scheduler(
            work_seconds=30,
            break_seconds=2,
            snooze_seconds=5,
            warning_seconds=10,
            monotonic=self.clocks.monotonic,
            wall_clock=self.clocks.wall_clock,
        )

    def test_warning_is_emitted_once_before_the_break(self):
        self.clocks.advance(19)
        self.assertIsNone(self.scheduler.advance())

        self.clocks.advance(1)
        self.assertEqual(self.scheduler.advance(), Transition.WARN_BREAK)
        self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)

        self.clocks.advance(1)
        self.assertIsNone(self.scheduler.advance())

    def test_break_deadline_takes_precedence_over_a_missed_warning(self):
        self.clocks.advance(30)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)

    def test_each_work_interval_warns_again(self):
        self.clocks.advance(20)
        self.assertEqual(self.scheduler.advance(), Transition.WARN_BREAK)
        self.clocks.advance(10)
        self.scheduler.advance()
        self.scheduler.skip_break()

        self.clocks.advance(20)
        self.assertEqual(self.scheduler.advance(), Transition.WARN_BREAK)

    def test_resuming_from_pause_can_warn_again(self):
        self.clocks.advance(20)
        self.assertEqual(self.scheduler.advance(), Transition.WARN_BREAK)
        self.scheduler.pause()
        self.scheduler.resume()

        self.clocks.advance(1)
        self.assertEqual(self.scheduler.advance(), Transition.WARN_BREAK)

    def test_disabled_warning_never_fires(self):
        scheduler = Scheduler(
            work_seconds=30,
            break_seconds=2,
            warning_seconds=0,
            monotonic=self.clocks.monotonic,
            wall_clock=self.clocks.wall_clock,
        )
        self.clocks.advance(29)
        self.assertIsNone(scheduler.advance())


class IdleCreditTests(SchedulerFixture):
    def test_idle_longer_than_a_break_restarts_the_work_interval(self):
        self.clocks.advance(20)
        self.assertTrue(self.scheduler.credit_idle_break(5))
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 30)

    def test_short_idle_does_not_count_as_a_break(self):
        self.clocks.advance(20)
        self.assertFalse(self.scheduler.credit_idle_break(1))
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 10)

    def test_idle_does_not_dismiss_an_enforced_break(self):
        self.scheduler.start_break()
        self.assertFalse(self.scheduler.credit_idle_break(600))
        self.assertEqual(self.scheduler.snapshot().phase, Phase.BREAK)

    def test_idle_does_not_resume_a_paused_timer(self):
        self.scheduler.pause()
        self.assertFalse(self.scheduler.credit_idle_break(600))
        self.assertEqual(self.scheduler.snapshot().phase, Phase.PAUSED)


if __name__ == "__main__":
    unittest.main()
