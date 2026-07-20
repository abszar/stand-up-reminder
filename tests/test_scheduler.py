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


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clocks = FakeClocks()
        self.scheduler = Scheduler(
            work_seconds=30,
            break_seconds=2,
            mode=TimingMode.ACTIVE,
            monotonic=self.clocks.monotonic,
            wall_clock=self.clocks.wall_clock,
        )

    def test_initial_work_interval(self):
        snapshot = self.scheduler.snapshot()
        self.assertEqual(snapshot.phase, Phase.WORK)
        self.assertEqual(snapshot.seconds_remaining, 30)

    def test_work_deadline_starts_break(self):
        self.clocks.advance(30)
        self.assertEqual(self.scheduler.advance(), Transition.START_BREAK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 2)

    def test_break_completion_resets_full_work_interval(self):
        self.scheduler.start_break()
        self.clocks.advance(2)
        self.assertEqual(self.scheduler.advance(), Transition.END_BREAK)
        self.assertEqual(self.scheduler.snapshot().phase, Phase.WORK)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 30)

    def test_manual_start_is_ignored_during_break(self):
        self.assertEqual(self.scheduler.start_break(), Transition.START_BREAK)
        self.assertIsNone(self.scheduler.start_break())

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

    def test_break_pauses_while_locked_for_both_modes(self):
        self.scheduler.set_mode(TimingMode.WALL)
        self.scheduler.start_break()
        self.scheduler.set_locked(True)
        self.clocks.advance(20)
        self.scheduler.advance()
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 2)

    def test_policy_change_preserves_remaining_time(self):
        self.clocks.advance(7)
        self.scheduler.set_mode(TimingMode.WALL)
        self.assertEqual(self.scheduler.snapshot().seconds_remaining, 23)


if __name__ == "__main__":
    unittest.main()
