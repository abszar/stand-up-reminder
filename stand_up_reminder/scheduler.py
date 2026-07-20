from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Phase(str, Enum):
    WORK = "work"
    SNOOZED = "snoozed"
    BREAK = "break"
    AWAITING_RETURN = "awaiting_return"
    PAUSED = "paused"


class TimingMode(str, Enum):
    ACTIVE = "active"
    WALL = "wall"


class Transition(str, Enum):
    START_BREAK = "start_break"
    BREAK_COMPLETE = "break_complete"
    END_BREAK = "end_break"
    WARN_BREAK = "warn_break"


@dataclass(frozen=True)
class Snapshot:
    phase: Phase
    seconds_remaining: int
    away_seconds: int
    locked: bool
    mode: TimingMode
    paused_indefinitely: bool = False


class Scheduler:
    def __init__(
        self,
        *,
        work_seconds: float = 30 * 60,
        break_seconds: float = 2 * 60,
        snooze_seconds: float = 5 * 60,
        warning_seconds: float = 0,
        mode: TimingMode = TimingMode.ACTIVE,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.work_seconds = float(work_seconds)
        self.break_seconds = float(break_seconds)
        self.snooze_seconds = float(snooze_seconds)
        self.warning_seconds = float(warning_seconds)
        self.mode = TimingMode(mode)
        self.phase = Phase.WORK
        self.remaining = self.work_seconds
        self.away_elapsed = 0.0
        self.locked = False
        self._warned = False
        self._held_work_remaining = self.work_seconds
        self._pause_is_timed = False
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._last_mono = monotonic()
        self._last_wall = wall_clock()

    def _elapsed(self) -> tuple[float, float]:
        now_mono = self._monotonic()
        now_wall = self._wall_clock()
        mono_delta = max(0.0, now_mono - self._last_mono)
        wall_delta = max(0.0, now_wall - self._last_wall)
        self._last_mono = now_mono
        self._last_wall = now_wall
        return mono_delta, wall_delta

    def _begin_work(self, remaining: Optional[float] = None) -> None:
        self.phase = Phase.WORK
        self.remaining = self.work_seconds if remaining is None else remaining
        self.away_elapsed = 0.0
        self._warned = False
        self._pause_is_timed = False

    def _begin_break(self) -> Transition:
        self.phase = Phase.BREAK
        self.remaining = self.break_seconds
        self.away_elapsed = 0.0
        self._warned = False
        return Transition.START_BREAK

    def advance(self) -> Optional[Transition]:
        mono_delta, wall_delta = self._elapsed()

        if self.phase is Phase.PAUSED:
            if not self._pause_is_timed:
                return None
            self.remaining = max(0.0, self.remaining - wall_delta)
            if self.remaining > 0:
                return None
            self._begin_work(self._held_work_remaining)
            return None

        if self.phase in (Phase.BREAK, Phase.AWAITING_RETURN):
            self.away_elapsed += wall_delta
            if self.phase is Phase.AWAITING_RETURN:
                return None
            self.remaining = max(0.0, self.remaining - wall_delta)
            if self.remaining > 0:
                return None
            self.phase = Phase.AWAITING_RETURN
            self.remaining = 0.0
            return Transition.BREAK_COMPLETE

        if self.phase is Phase.SNOOZED:
            self.remaining = max(0.0, self.remaining - wall_delta)
            if self.remaining > 0:
                return None
            return self._begin_break()

        if self.locked:
            if self.mode is TimingMode.WALL:
                self.remaining = max(0.0, self.remaining - wall_delta)
            return None

        delta = wall_delta if self.mode is TimingMode.WALL else mono_delta
        self.remaining = max(0.0, self.remaining - delta)
        if self.remaining > 0:
            if (
                self.warning_seconds > 0
                and not self._warned
                and self.remaining <= self.warning_seconds
            ):
                self._warned = True
                return Transition.WARN_BREAK
            return None

        return self._begin_break()

    def start_break(self) -> Optional[Transition]:
        transition = self.advance()
        if self.phase in (
            Phase.SNOOZED,
            Phase.BREAK,
            Phase.AWAITING_RETURN,
        ):
            return transition
        return self._begin_break()

    def snooze_break(self) -> bool:
        self.advance()
        if self.phase is not Phase.BREAK:
            return False
        self.phase = Phase.SNOOZED
        self.remaining = self.snooze_seconds
        self.away_elapsed = 0.0
        return True

    def skip_break(self) -> bool:
        self.advance()
        if self.phase is not Phase.BREAK:
            return False
        self._begin_work()
        return True

    def confirm_return(self) -> Optional[Transition]:
        transition = self.advance()
        if self.phase is not Phase.AWAITING_RETURN:
            return transition
        self._begin_work()
        return Transition.END_BREAK

    def reset_work_interval(self) -> bool:
        self.advance()
        if self.phase in (Phase.SNOOZED, Phase.BREAK, Phase.PAUSED):
            return False
        if self.phase is Phase.AWAITING_RETURN:
            return self.confirm_return() is Transition.END_BREAK
        self.remaining = self.work_seconds
        self._warned = False
        return True

    def pause(self, duration_seconds: Optional[float] = None) -> bool:
        """Hold the work interval, either indefinitely or for a fixed time.

        Pausing is refused during a break, a snooze, or a pending return so
        that it cannot be used to dismiss a break that is already due.
        """
        self.advance()
        if self.phase is not Phase.WORK:
            return False
        self._held_work_remaining = self.remaining
        self.phase = Phase.PAUSED
        self._pause_is_timed = duration_seconds is not None
        self.remaining = 0.0 if duration_seconds is None else float(duration_seconds)
        return True

    def resume(self) -> bool:
        self.advance()
        if self.phase is not Phase.PAUSED:
            return False
        self._begin_work(self._held_work_remaining)
        return True

    def set_durations(
        self,
        *,
        work_seconds: Optional[float] = None,
        break_seconds: Optional[float] = None,
        snooze_seconds: Optional[float] = None,
        warning_seconds: Optional[float] = None,
    ) -> None:
        """Apply new durations, leaving any break that is already running.

        A changed work length restarts the current work interval so that the
        indicator immediately reflects the choice the user just made. A paused
        timer keeps its held interval updated without resuming.
        """
        self.advance()
        if break_seconds is not None:
            self.break_seconds = float(break_seconds)
        if snooze_seconds is not None:
            self.snooze_seconds = float(snooze_seconds)
        if warning_seconds is not None:
            self.warning_seconds = float(warning_seconds)
            self._warned = False
        if work_seconds is None or float(work_seconds) == self.work_seconds:
            return
        self.work_seconds = float(work_seconds)
        self._warned = False
        self._held_work_remaining = self.work_seconds
        if self.phase is Phase.WORK:
            self.remaining = self.work_seconds

    def credit_idle_break(self, idle_seconds: float) -> bool:
        """Treat a long idle stretch as a break that was already taken."""
        self.advance()
        if self.phase is not Phase.WORK or idle_seconds < self.break_seconds:
            return False
        self.remaining = self.work_seconds
        self._warned = False
        return True

    def set_locked(self, locked: bool) -> Optional[Transition]:
        transition = self.advance()
        self.locked = bool(locked)
        if not self.locked:
            return self.advance() or transition
        return transition

    def set_mode(self, mode: TimingMode) -> Optional[Transition]:
        transition = self.advance()
        self.mode = TimingMode(mode)
        return transition

    def snapshot(self) -> Snapshot:
        return Snapshot(
            phase=self.phase,
            away_seconds=int(math.floor(max(0.0, self.away_elapsed))),
            seconds_remaining=int(math.ceil(max(0.0, self.remaining))),
            locked=self.locked,
            mode=self.mode,
            paused_indefinitely=(
                self.phase is Phase.PAUSED and not self._pause_is_timed
            ),
        )
