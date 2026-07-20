import json
import tempfile
import unittest
from pathlib import Path

from stand_up_reminder.scheduler import TimingMode
from stand_up_reminder.settings import Settings, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "nested" / "settings.json"
        self.store = SettingsStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_file_uses_active_default(self):
        self.assertEqual(self.store.load(), Settings(TimingMode.ACTIVE))

    def test_malformed_file_uses_active_default(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(self.store.load(), Settings(TimingMode.ACTIVE))

    def test_unknown_mode_uses_active_default(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"timing_mode": "unknown"}), encoding="utf-8")
        self.assertEqual(self.store.load(), Settings(TimingMode.ACTIVE))

    def test_save_round_trip(self):
        self.store.save(Settings(TimingMode.WALL))
        self.assertEqual(self.store.load(), Settings(TimingMode.WALL))
        self.assertFalse(self.path.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
