import json
import tempfile
import unittest
from pathlib import Path

from stand_up_reminder.scheduler import TimingMode
from stand_up_reminder.settings import (
    BREAK_SECONDS_RANGE,
    SNOOZE_SECONDS_RANGE,
    WORK_SECONDS_RANGE,
    Settings,
    SettingsStore,
)


class SettingsDefaultsTests(unittest.TestCase):
    def test_defaults_match_documented_cycle(self):
        settings = Settings()
        self.assertEqual(settings.mode, TimingMode.ACTIVE)
        self.assertEqual(settings.work_seconds, 30 * 60)
        self.assertEqual(settings.break_seconds, 2 * 60)
        self.assertEqual(settings.snooze_seconds, 5 * 60)
        self.assertEqual(settings.warning_seconds, 60)
        self.assertTrue(settings.idle_reset_enabled)
        self.assertTrue(settings.show_countdown)
        self.assertFalse(settings.sound_enabled)


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "nested" / "settings.json"
        self.store = SettingsStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_missing_file_uses_defaults(self):
        self.assertEqual(self.store.load(), Settings())

    def test_malformed_file_uses_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(self.store.load(), Settings())

    def test_unknown_mode_uses_active_default(self):
        self.write({"timing_mode": "unknown"})
        self.assertEqual(self.store.load().mode, TimingMode.ACTIVE)

    def test_reads_a_settings_file_written_before_durations_existed(self):
        self.write({"timing_mode": "wall"})
        settings = self.store.load()
        self.assertEqual(settings.mode, TimingMode.WALL)
        self.assertEqual(settings.work_seconds, Settings().work_seconds)

    def test_save_round_trip(self):
        saved = Settings(
            mode=TimingMode.WALL,
            work_seconds=45 * 60,
            break_seconds=3 * 60,
            snooze_seconds=10 * 60,
            warning_seconds=0,
            idle_reset_enabled=False,
            show_countdown=False,
            sound_enabled=True,
        )
        self.store.save(saved)
        self.assertEqual(self.store.load(), saved)
        self.assertFalse(self.path.with_suffix(".tmp").exists())

    def test_out_of_range_durations_are_clamped(self):
        self.write({"work_seconds": 9_999_999, "break_seconds": 0})
        settings = self.store.load()
        self.assertEqual(settings.work_seconds, WORK_SECONDS_RANGE[1])
        self.assertEqual(settings.break_seconds, BREAK_SECONDS_RANGE[0])

    def test_non_numeric_durations_fall_back_to_defaults(self):
        self.write({"work_seconds": "half an hour", "snooze_seconds": None})
        settings = self.store.load()
        self.assertEqual(settings.work_seconds, Settings().work_seconds)
        self.assertEqual(settings.snooze_seconds, Settings().snooze_seconds)

    def test_warning_longer_than_work_interval_is_clamped(self):
        self.write({"work_seconds": 300, "warning_seconds": 600})
        self.assertLess(
            self.store.load().warning_seconds, self.store.load().work_seconds
        )

    def test_snooze_range_is_enforced(self):
        self.write({"snooze_seconds": 1})
        self.assertEqual(self.store.load().snooze_seconds, SNOOZE_SECONDS_RANGE[0])

    def test_non_boolean_flags_fall_back_to_defaults(self):
        self.write({"sound_enabled": "yes", "show_countdown": 3})
        settings = self.store.load()
        self.assertFalse(settings.sound_enabled)
        self.assertTrue(settings.show_countdown)

    def test_corrupt_field_does_not_discard_valid_fields(self):
        self.write({"timing_mode": "wall", "work_seconds": "bogus"})
        self.assertEqual(self.store.load().mode, TimingMode.WALL)


if __name__ == "__main__":
    unittest.main()
