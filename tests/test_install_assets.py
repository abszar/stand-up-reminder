import configparser
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallAssetTests(unittest.TestCase):
    def _desktop(self, name):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(ROOT / "data" / name, encoding="utf-8")
        return parser["Desktop Entry"]

    def test_application_launcher_starts_user_service(self):
        entry = self._desktop("stand-up-reminder.desktop")
        self.assertEqual(entry["Type"], "Application")
        self.assertEqual(
            entry["Exec"], "systemctl --user start stand-up-reminder.service"
        )
        self.assertEqual(entry["Icon"], "stand-up-reminder-symbolic")

    def test_autostart_is_enabled(self):
        entry = self._desktop("stand-up-reminder-autostart.desktop")
        self.assertEqual(entry["X-GNOME-Autostart-enabled"], "true")
        self.assertEqual(entry["NoDisplay"], "true")

    def test_service_restarts_only_on_failure(self):
        service = (ROOT / "data" / "stand-up-reminder.service").read_text()
        self.assertIn("ExecStart=%h/.local/bin/stand-up-reminder", service)
        self.assertIn("Restart=on-failure", service)
        self.assertNotIn("Restart=always", service)

    def test_launcher_executes_installed_python_package(self):
        launcher = (ROOT / "data" / "stand-up-reminder-launcher").read_text()
        self.assertIn("/usr/bin/python3", launcher)
        self.assertIn("-m stand_up_reminder", launcher)
        self.assertIn('cd "$app_install_root"', launcher)

    def test_install_and_uninstall_scripts_are_strict(self):
        for name in ("install.sh", "uninstall.sh"):
            script = (ROOT / "scripts" / name).read_text()
            self.assertTrue(script.startswith("#!/bin/sh\nset -eu\n"))


if __name__ == "__main__":
    unittest.main()
