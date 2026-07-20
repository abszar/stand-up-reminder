from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .scheduler import TimingMode


DEFAULT_WORK_SECONDS = 30 * 60
DEFAULT_BREAK_SECONDS = 2 * 60
DEFAULT_SNOOZE_SECONDS = 5 * 60
DEFAULT_WARNING_SECONDS = 60

WORK_SECONDS_RANGE = (60, 4 * 60 * 60)
BREAK_SECONDS_RANGE = (15, 60 * 60)
SNOOZE_SECONDS_RANGE = (60, 60 * 60)
WARNING_SECONDS_RANGE = (0, 15 * 60)

WORK_PRESETS = (20 * 60, 25 * 60, 30 * 60, 45 * 60, 60 * 60)
BREAK_PRESETS = (60, 2 * 60, 5 * 60, 10 * 60)


@dataclass(frozen=True)
class Settings:
    mode: TimingMode = TimingMode.ACTIVE
    work_seconds: int = DEFAULT_WORK_SECONDS
    break_seconds: int = DEFAULT_BREAK_SECONDS
    snooze_seconds: int = DEFAULT_SNOOZE_SECONDS
    warning_seconds: int = DEFAULT_WARNING_SECONDS
    idle_reset_enabled: bool = True
    show_countdown: bool = True
    sound_enabled: bool = False


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return max(low, min(high, value))


def _read_duration(payload: dict, key: str, bounds: tuple[int, int], default: int) -> int:
    raw = payload.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return default
    return _clamp(int(raw), bounds)


def _read_flag(payload: dict, key: str, default: bool) -> bool:
    raw = payload.get(key, default)
    return raw if isinstance(raw, bool) else default


def _read_mode(payload: dict) -> TimingMode:
    try:
        return TimingMode(payload["timing_mode"])
    except (KeyError, ValueError):
        return TimingMode.ACTIVE


def settings_from_payload(payload: dict) -> Settings:
    """Build settings from stored JSON, ignoring any field that is unusable.

    Each field falls back independently so that one corrupt value never
    discards the rest of a user's configuration.
    """
    work_seconds = _read_duration(
        payload, "work_seconds", WORK_SECONDS_RANGE, DEFAULT_WORK_SECONDS
    )
    warning_seconds = _read_duration(
        payload, "warning_seconds", WARNING_SECONDS_RANGE, DEFAULT_WARNING_SECONDS
    )
    return Settings(
        mode=_read_mode(payload),
        work_seconds=work_seconds,
        break_seconds=_read_duration(
            payload, "break_seconds", BREAK_SECONDS_RANGE, DEFAULT_BREAK_SECONDS
        ),
        snooze_seconds=_read_duration(
            payload, "snooze_seconds", SNOOZE_SECONDS_RANGE, DEFAULT_SNOOZE_SECONDS
        ),
        # A warning can never precede the interval that triggers it.
        warning_seconds=min(warning_seconds, work_seconds - 1),
        idle_reset_enabled=_read_flag(payload, "idle_reset_enabled", True),
        show_countdown=_read_flag(payload, "show_countdown", True),
        sound_enabled=_read_flag(payload, "sound_enabled", False),
    )


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("settings file is not an object")
            return settings_from_payload(payload)
        except (OSError, ValueError, TypeError) as error:
            if self.path.exists():
                print(
                    f"stand-up-reminder: using default settings: {error}",
                    file=sys.stderr,
                )
            return Settings()

    def save(self, settings: Settings) -> None:
        payload = asdict(settings)
        payload["timing_mode"] = payload.pop("mode").value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            finally:
                raise
