import json
import tempfile
import unittest
from pathlib import Path

from stand_up_reminder.scheduler import TimingMode
from stand_up_reminder.settings import (
    BREAK_SECONDS_RANGE,
    IDLE_CREDIT_SECONDS_RANGE,
    SNOOZE_SECONDS_RANGE,
    WORK_SECONDS_RANGE,
    Settings,
    SettingsStore,
    settings_from_payload,
)


class SettingsDefaultsTests(unittest.TestCase):
    def test_defaults_match_documented_cycle(self):
        settings = Settings()
        self.assertEqual(settings.mode, TimingMode.ACTIVE)
        self.assertEqual(settings.work_seconds, 30 * 60)
        self.assertEqual(settings.break_seconds, 2 * 60)
        self.assertEqual(settings.snooze_seconds, 5 * 60)
        self.assertEqual(settings.warning_seconds, 15)
        self.assertEqual(settings.idle_credit_seconds, 10 * 60)
        self.assertTrue(settings.idle_reset_enabled)
        self.assertTrue(settings.show_countdown)
        self.assertFalse(settings.sound_enabled)
        self.assertEqual(settings.standing_pill_position, 0.5)


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
            idle_credit_seconds=15 * 60,
            idle_reset_enabled=False,
            show_countdown=False,
            sound_enabled=True,
            muted_sounds=frozenset({"break_done"}),
            standing_pill_position=0.2,
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

    def test_idle_credit_range_is_enforced(self):
        self.write({"idle_credit_seconds": 1})
        self.assertEqual(
            self.store.load().idle_credit_seconds, IDLE_CREDIT_SECONDS_RANGE[0]
        )

    def test_settings_file_without_idle_credit_uses_the_default(self):
        self.write({"timing_mode": "wall"})
        self.assertEqual(
            self.store.load().idle_credit_seconds, Settings().idle_credit_seconds
        )

    def test_non_boolean_flags_fall_back_to_defaults(self):
        self.write({"sound_enabled": "yes", "show_countdown": 3})
        settings = self.store.load()
        self.assertFalse(settings.sound_enabled)
        self.assertTrue(settings.show_countdown)

    def test_standing_pill_position_is_clamped_to_the_screen(self):
        self.write({"standing_pill_position": 1.8})
        self.assertEqual(self.store.load().standing_pill_position, 1.0)
        self.write({"standing_pill_position": -0.4})
        self.assertEqual(self.store.load().standing_pill_position, 0.0)

    def test_non_numeric_standing_pill_position_falls_back_to_the_default(self):
        self.write({"standing_pill_position": "top"})
        self.assertEqual(
            self.store.load().standing_pill_position,
            Settings().standing_pill_position,
        )

    def test_corrupt_field_does_not_discard_valid_fields(self):
        self.write({"timing_mode": "wall", "work_seconds": "bogus"})
        self.assertEqual(self.store.load().mode, TimingMode.WALL)


class MutedSoundTests(unittest.TestCase):
    def test_nothing_is_muted_to_begin_with(self):
        self.assertEqual(Settings().muted_sounds, frozenset())

    def test_a_stored_list_of_keys_is_read_back(self):
        settings = settings_from_payload({"muted_sounds": ["break_done"]})
        self.assertEqual(settings.muted_sounds, frozenset({"break_done"}))

    def test_a_value_that_is_not_a_list_of_names_is_ignored(self):
        self.assertEqual(
            settings_from_payload({"muted_sounds": "break_done"}).muted_sounds,
            frozenset(),
        )
        self.assertEqual(
            settings_from_payload({"muted_sounds": [1, None]}).muted_sounds,
            frozenset(),
        )

    def test_unknown_names_are_kept_so_a_cue_survives_being_renamed_back(self):
        settings = settings_from_payload({"muted_sounds": ["not_a_cue_yet"]})
        self.assertEqual(settings.muted_sounds, frozenset({"not_a_cue_yet"}))


if __name__ == "__main__":
    unittest.main()
