from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicationDocumentTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_mit_license_names_copyright_holder(self):
        license_text = self.read("LICENSE")
        self.assertIn("MIT License", license_text)
        self.assertIn(
            "Copyright (c) 2026 Abdelali Bourassine", license_text
        )
        self.assertIn("Permission is hereby granted", license_text)

    def test_readme_has_complete_ubuntu_installation_flow(self):
        readme = self.read("README.md")
        required_text = (
            "Ubuntu 24.04",
            "GNOME Shell 46",
            "gir1.2-ayatanaappindicator3-0.1",
            "git clone https://github.com/abszar/stand-up-reminder.git",
            "scripts/install.sh",
            "systemctl --user status stand-up-reminder.service",
            "git pull --ff-only",
            "scripts/uninstall.sh",
        )
        for text in required_text:
            with self.subTest(text=text):
                self.assertIn(text, readme)

    def test_readme_lists_git_as_a_system_dependency(self):
        readme = self.read("README.md")
        dependency_block = readme.split("sudo apt install \\", 1)[1].split(
            "```", 1
        )[0]
        self.assertRegex(dependency_block, r"(?m)^  git \\\s*$")

    def test_readme_explains_user_local_installation_scope(self):
        readme = self.read("README.md")
        normalized_readme = " ".join(readme.split())
        self.assertIn(
            "Application files are installed for the current user; installing "
            "the required Ubuntu packages uses `sudo`.",
            normalized_readme,
        )

    def test_readme_has_substantive_troubleshooting_guidance(self):
        readme = self.read("README.md")
        required_text = (
            "## Troubleshooting",
            "systemctl --user status stand-up-reminder.service",
            "journalctl --user -u stand-up-reminder.service",
            "systemctl --user restart stand-up-reminder.service",
            "AppIndicator extension",
            "sign out and back in",
            "No module named 'gi'",
            "python3-gi",
            "gir1.2-gtk-3.0",
            "gir1.2-ayatanaappindicator3-0.1",
        )
        for text in required_text:
            with self.subTest(text=text):
                self.assertIn(text, readme)

    def test_public_tracked_text_has_only_github_noreply_addresses(self):
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        email_pattern = re.compile(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
        )

        for raw_path in filter(None, tracked):
            relative_path = raw_path.decode("utf-8")
            contents = self.read(relative_path)
            for match in email_pattern.finditer(contents):
                with self.subTest(path=relative_path, address=match.group(0)):
                    self.assertTrue(
                        match.group(0).endswith("@users.noreply.github.com")
                    )

    def test_changelog_describes_version_1_0_0(self):
        changelog = self.read("CHANGELOG.md")
        self.assertIn("## [1.0.0] - 2026-07-20", changelog)
        self.assertIn("five-minute snoozing", changelog)
        self.assertIn("Ubuntu GNOME", changelog)

    def test_gitignore_covers_python_and_local_agent_artifacts(self):
        patterns = self.read(".gitignore").splitlines()
        self.assertIn("__pycache__/", patterns)
        self.assertIn("*.py[cod]", patterns)
        self.assertIn(".venv/", patterns)
        self.assertIn(".superpowers/", patterns)


if __name__ == "__main__":
    unittest.main()
