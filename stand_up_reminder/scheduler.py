from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Phase(str, Enum):
    WORK = "work"
    BREAK = "break"


class TimingMode(str, Enum):
    ACTIVE = "active"
    WALL = "wall"


class Transition(str, Enum):
    START_BREAK = "start_break"
    END_BREAK = "end_break"


@dataclass(frozen=True)
class Snapshot:
    phase: Phase
    seconds_remaining: int
    locked: bool
    mode: TimingMode


class Scheduler:
    def __init__(
        self,
        *,
        work_seconds: float = 30 * 60,
        break_seconds: float = 2 * 60,
        mode: TimingMode = TimingMode.ACTIVE,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.work_seconds = float(work_seconds)
        self.break_seconds = float(break_seconds)
        self.mode = TimingMode(mode)
        self.phase = Phase.WORK
        self.remaining = self.work_seconds
        self.locked = False
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

    def advance(self) -> Optional[Transition]:
        mono_delta, wall_delta = self._elapsed()

        if self.locked:
            if self.phase is Phase.WORK and self.mode is TimingMode.WALL:
                self.remaining = max(0.0, self.remaining - wall_delta)
            return None

        delta = mono_delta
        if self.phase is Phase.WORK and self.mode is TimingMode.WALL:
            delta = wall_delta
        self.remaining = max(0.0, self.remaining - delta)

        if self.remaining > 0:
            return None
        if self.phase is Phase.WORK:
            self.phase = Phase.BREAK
            self.remaining = self.break_seconds
            return Transition.START_BREAK

        self.phase = Phase.WORK
        self.remaining = self.work_seconds
        return Transition.END_BREAK

    def start_break(self) -> Optional[Transition]:
        transition = self.advance()
        if self.phase is Phase.BREAK:
            return transition
        self.phase = Phase.BREAK
        self.remaining = self.break_seconds
        return Transition.START_BREAK

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
            seconds_remaining=int(math.ceil(max(0.0, self.remaining))),
            locked=self.locked,
            mode=self.mode,
        )
