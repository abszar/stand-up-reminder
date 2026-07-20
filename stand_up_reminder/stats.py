from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional

from .i18n import _, ngettext


HISTORY_DAYS = 30


class BreakOutcome(str, Enum):
    TAKEN = "taken"
    SKIPPED = "skipped"
    SNOOZED = "snoozed"


@dataclass(frozen=True)
class DailyStats:
    taken: int = 0
    skipped: int = 0
    snoozed: int = 0


def today_key(today: Optional[str] = None) -> str:
    return today or date.today().isoformat()


def summary_label(stats: DailyStats) -> str:
    if not (stats.taken or stats.skipped or stats.snoozed):
        return _("No breaks yet today")
    parts = []
    if stats.taken:
        parts.append(
            ngettext("%d break taken", "%d breaks taken", stats.taken) % stats.taken
        )
    if stats.skipped:
        parts.append(_("%d skipped") % stats.skipped)
    if stats.snoozed:
        parts.append(_("%d snoozed") % stats.snoozed)
    return _("Today: %s") % ", ".join(parts)


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

    def load(self, today: Optional[str] = None) -> DailyStats:
        entry = self._read_days().get(today_key(today), {})
        if not isinstance(entry, dict):
            return DailyStats()
        return DailyStats(
            taken=_counter(entry, "taken"),
            skipped=_counter(entry, "skipped"),
            snoozed=_counter(entry, "snoozed"),
        )

    def record(self, outcome: BreakOutcome, today: Optional[str] = None) -> None:
        key = today_key(today)
        days = self._read_days()
        entry = days.get(key)
        days[key] = entry if isinstance(entry, dict) else {}
        days[key][outcome.value] = _counter(days[key], outcome.value) + 1
        for stale in sorted(days)[:-HISTORY_DAYS]:
            del days[stale]
        self._write(days)

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
