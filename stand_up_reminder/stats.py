from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .i18n import _, ngettext


HISTORY_DAYS = 30
WEEK_DAYS = 7


class BreakOutcome(str, Enum):
    TAKEN = "taken"
    AWAY = "away"
    MISSED = "missed"
    SKIPPED = "skipped"
    SNOOZED = "snoozed"


@dataclass(frozen=True)
class DailyStats:
    taken: int = 0
    away: int = 0
    missed: int = 0
    skipped: int = 0
    snoozed: int = 0


def today_key(today: Optional[str] = None) -> str:
    return today or date.today().isoformat()


def _outcome_parts(stats: DailyStats) -> list[str]:
    parts = []
    if stats.taken:
        parts.append(
            ngettext("%d break taken", "%d breaks taken", stats.taken) % stats.taken
        )
    if stats.away:
        parts.append(_("%d away") % stats.away)
    if stats.missed:
        parts.append(_("%d missed") % stats.missed)
    if stats.skipped:
        parts.append(_("%d skipped") % stats.skipped)
    if stats.snoozed:
        parts.append(_("%d snoozed") % stats.snoozed)
    return parts


def summary_label(stats: DailyStats) -> str:
    parts = _outcome_parts(stats)
    if not parts:
        return _("No breaks yet today")
    return _("Today: %s") % ", ".join(parts)


def week_label(stats: DailyStats) -> str:
    parts = _outcome_parts(stats)
    if not parts:
        return _("No breaks this week")
    return _("This week: %s") % ", ".join(parts)


def last_days(count: int, today: Optional[str] = None) -> list[str]:
    """ISO day keys for a rolling window, oldest first, ending today."""
    end = date.fromisoformat(today_key(today))
    return [
        (end - timedelta(days=offset)).isoformat()
        for offset in range(count - 1, -1, -1)
    ]


def aggregate_stats(days: Iterable[DailyStats]) -> DailyStats:
    total = DailyStats()
    for stats in days:
        total = DailyStats(
            taken=total.taken + stats.taken,
            away=total.away + stats.away,
            missed=total.missed + stats.missed,
            skipped=total.skipped + stats.skipped,
            snoozed=total.snoozed + stats.snoozed,
        )
    return total


def adherence_percent(stats: DailyStats) -> Optional[int]:
    """Share of due breaks that were taken; away and snoozed stay neutral.

    Idle credits prove nothing on a desk with a second computer, and a
    snoozed break always resolves into another outcome later.
    """
    due = stats.taken + stats.missed + stats.skipped
    if due <= 0:
        return None
    return round(100 * stats.taken / due)


def score_emoji(percent: int) -> str:
    if percent >= 90:
        return "😄"
    if percent >= 70:
        return "🙂"
    if percent >= 40:
        return "😐"
    return "😟"


def _score_part(percent: Optional[int]) -> str:
    if percent is None:
        return "—"
    return f"{percent}% {score_emoji(percent)}"


def score_line(
    today_percent: Optional[int], week_percent: Optional[int]
) -> str:
    """One-line day and week adherence summary for the break window."""
    return " · ".join(
        (
            _("Today: %s") % _score_part(today_percent),
            _("This week: %s") % _score_part(week_percent),
        )
    )


def _event_minutes(raw: str) -> Optional[int]:
    try:
        hours, minutes = raw.split(":")
        value = int(hours) * 60 + int(minutes)
    except (AttributeError, TypeError, ValueError):
        return None
    if not 0 <= value < 24 * 60:
        return None
    return value


def timeline_layout(
    events: Sequence[tuple[int, str]], now_minutes: int
) -> tuple[int, int, list[tuple[float, str]]]:
    """Day-axis positions for the outcome dots.

    The track spans whole hours, from the first event (or now, on a quiet
    day) up to the later of the last event and the present moment, so the
    dots spread over the part of the day that was actually worked.
    """
    times = [minutes for minutes, _outcome in events]
    start = (min(times + [now_minutes]) // 60) * 60
    end_raw = max(times + [now_minutes])
    end = -(-end_raw // 60) * 60
    if end <= start:
        end = start + 60
    span = end - start
    points = [
        (min(1.0, max(0.0, (minutes - start) / span)), outcome)
        for minutes, outcome in events
    ]
    return start, end, points


def rating_label(percent: Optional[int]) -> str:
    if percent is None:
        return _("No breaks due yet")
    if percent >= 90:
        return _("Excellent — you rarely miss a break")
    if percent >= 70:
        return _("Good — most breaks taken")
    if percent >= 40:
        return _("Could be better — many breaks slip by")
    return _("Time to stand up more often")


def _counter(payload: dict, key: str) -> int:
    raw = payload.get(key, 0)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return 0
    return raw


class StatsStore:
    """Break counters per day, kept in a small rolling JSON file.

    Statistics are strictly informational, so every failure path degrades to
    empty counters rather than interrupting the reminder cycle.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _read_days(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            days = payload["days"]
            return days if isinstance(days, dict) else {}
        except (OSError, ValueError, TypeError, KeyError):
            return {}

    @staticmethod
    def _entry_stats(entry) -> DailyStats:
        if not isinstance(entry, dict):
            return DailyStats()
        return DailyStats(
            taken=_counter(entry, "taken"),
            away=_counter(entry, "away"),
            missed=_counter(entry, "missed"),
            skipped=_counter(entry, "skipped"),
            snoozed=_counter(entry, "snoozed"),
        )

    def load(self, today: Optional[str] = None) -> DailyStats:
        return self._entry_stats(self._read_days().get(today_key(today), {}))

    def load_days(self, days: Sequence[str]) -> list[DailyStats]:
        """Stats for several days, read from the file once."""
        stored = self._read_days()
        return [self._entry_stats(stored.get(day, {})) for day in days]

    def record(
        self,
        outcome: BreakOutcome,
        today: Optional[str] = None,
        at: Optional[str] = None,
    ) -> None:
        key = today_key(today)
        days = self._read_days()
        entry = days.get(key)
        days[key] = entry if isinstance(entry, dict) else {}
        days[key][outcome.value] = _counter(days[key], outcome.value) + 1
        events = days[key].get("events")
        days[key]["events"] = events if isinstance(events, list) else []
        days[key]["events"].append(
            [at or datetime.now().strftime("%H:%M"), outcome.value]
        )
        for stale in sorted(days)[:-HISTORY_DAYS]:
            del days[stale]
        self._write(days)

    def load_events(self, today: Optional[str] = None) -> list[tuple[int, str]]:
        """The day's outcomes with their minute of the day, oldest first."""
        entry = self._read_days().get(today_key(today), {})
        if not isinstance(entry, dict) or not isinstance(
            entry.get("events"), list
        ):
            return []
        events = []
        for item in entry["events"]:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            raw_time, outcome = item
            minutes = _event_minutes(raw_time)
            if minutes is None or not isinstance(outcome, str):
                continue
            events.append((minutes, outcome))
        return events

    def _write(self, days: dict) -> None:
        temporary = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"days": days}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
