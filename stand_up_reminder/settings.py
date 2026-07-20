from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .scheduler import TimingMode


@dataclass(frozen=True)
class Settings:
    mode: TimingMode = TimingMode.ACTIVE


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return Settings(mode=TimingMode(payload["timing_mode"]))
        except (OSError, ValueError, TypeError, KeyError) as error:
            if self.path.exists():
                print(
                    f"stand-up-reminder: using default settings: {error}",
                    file=sys.stderr,
                )
            return Settings()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps({"timing_mode": settings.mode.value}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            finally:
                raise
