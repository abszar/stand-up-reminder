# GitHub Publication and v1.0.0 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the application as the public `abszar/stand-up-reminder` GitHub repository with an MIT license, complete Ubuntu installation guide, privacy-safe history, and stable `v1.0.0` release.

**Architecture:** First make the tracked tree publication-ready and test its required documentation. Then validate and rewrite only unpublished author/committer email metadata with two independent local recovery points. Create and verify the public repository before tagging and publishing a source-only GitHub release.

**Tech Stack:** Git 2.43, GitHub CLI 2.94, Python 3 `unittest`, Markdown, systemd user service, Ubuntu 24.04.

## Global Constraints

- Repository: `abszar/stand-up-reminder`.
- Visibility: public.
- Default branch: `master`.
- Description: `A native Ubuntu Linux break reminder for GNOME that encourages two-minute standing breaks every 30 minutes.`
- Topics: `ubuntu`, `linux`, `gnome`, `gtk`, `python`, `productivity`, and `break-reminder`.
- License: MIT, copyright 2026 Abdelali Bourassine.
- Release tag: `v1.0.0`; release title: `Stand Up Reminder v1.0.0`.
- Preserve commit names, messages, timestamps, contents, and ordering; rewrite only author and committer email metadata to the authenticated `abszar` GitHub noreply address.
- Create and verify a local backup ref and Git bundle before rewriting history.
- Never force-push after the initial publication without explicit user approval.
- Use GitHub-generated source archives only; do not upload binary or custom archive assets.
- Limit compatibility claims to Ubuntu 24.04, GNOME Shell 46, and X11.
- Do not add dependencies, GitHub Actions, packaging formats, screenshots, issue templates, or a contribution guide.
- After the update, run `scripts/install.sh` and verify the installed package and user service as required by `AGENTS.md`.

---

### Task 1: Public documentation, license, and repository hygiene

**Files:**
- Create: `tests/test_publication_docs.py`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `CHANGELOG.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing install/uninstall scripts and documented application behavior.
- Produces: tested public documentation and repository files consumed by GitHub and the `v1.0.0` release.

- [ ] **Step 1: Write failing publication-document tests**

Create `tests/test_publication_docs.py`:

```python
from pathlib import Path
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
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_publication_docs -v
```

Expected: FAIL because `LICENSE`, `CHANGELOG.md`, and `.gitignore` do not exist and README lacks the full installation flow.

- [ ] **Step 3: Add the MIT license**

Create `LICENSE`:

```text
MIT License

Copyright (c) 2026 Abdelali Bourassine

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Add repository ignore rules**

Create `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
*$py.class

.venv/
venv/
env/

.coverage
.coverage.*
htmlcov/
.pytest_cache/
.mypy_cache/
.ruff_cache/

build/
dist/
*.egg-info/

.vscode/
.idea/
.DS_Store

.superpowers/
```

- [ ] **Step 5: Add the changelog**

Create `CHANGELOG.md`:

```markdown
# Changelog

All notable changes to Stand Up Reminder are documented in this file.

## [1.0.0] - 2026-07-20

### Added

- Native Ubuntu GNOME top-bar indicator and centered standing-break window.
- Deterministic 30-minute work and two-minute break cycle.
- Repeatable five-minute snoozing and full-break skipping.
- Explicit return confirmation after a completed break.
- Active-time and wall-clock timing modes for lock and suspend behavior.
- Graphical-login startup, Applications menu launcher, and clean Quit flow.
- User-local install, update, and uninstall scripts.
- Automated scheduler, presentation, settings, and installation tests.
```

- [ ] **Step 6: Replace README with the public guide**

Replace `README.md` with:

```markdown
# Stand Up Reminder

Stand Up Reminder is a native Ubuntu Linux application for GNOME that prompts
you to take a two-minute standing break after every 30 minutes of work. It runs
as a lightweight GTK application with a top-bar indicator and an always-on-top
break window.

## Features

- Fixed 30-minute work intervals and two-minute standing breaks.
- **Give me 5 minutes** snooze that can be repeated and returns with a fresh
  two-minute countdown.
- **Skip this break** action that immediately starts a new work interval.
- Explicit return confirmation after a completed break.
- Active-time or wall-clock handling for lock and suspend periods.
- GNOME top-bar status and controls.
- Automatic startup at graphical login.
- User-local installation without administrator access.

## Compatibility

Tested on Ubuntu 24.04 LTS, GNOME Shell 46, and X11. Other Ubuntu releases,
GNOME versions, Wayland sessions, and desktop environments are not verified.

## Install on Ubuntu

### 1. Install system dependencies

```bash
sudo apt update
sudo apt install \
  python3 \
  python3-gi \
  gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 \
  gnome-shell-extension-appindicator \
  desktop-file-utils
```

### 2. Clone and install

```bash
git clone https://github.com/abszar/stand-up-reminder.git
cd stand-up-reminder
scripts/install.sh
```

The installer copies the application into user-local directories, installs
the launcher and icons, configures login startup, and starts the user service.

### 3. Verify it is running

```bash
systemctl --user status stand-up-reminder.service
```

The service should report `active (running)`, and the icon should appear in
the GNOME top bar.

## Update an existing installation

```bash
git pull --ff-only
scripts/install.sh
```

The installer replaces the user-local copy and restarts the service.

## Controls

Open the top-bar indicator to see the next break, start a break immediately,
restart after a longer absence, select lock/suspend timing, or quit.

During the two-minute countdown:

- **Give me 5 minutes** returns five wall-clock minutes later with a fresh
  two-minute countdown and can be repeated.
- **Skip this break** immediately starts a fresh 30-minute work interval.

At `00:00`, the popup changes to **Break complete** and shows
**I'm back — start 30-minute timer**. Work resumes when return is confirmed.

## Timing modes

- **Active time only** pauses work timing while locked and excludes suspend.
- **Wall-clock time** counts lock and suspend; overdue breaks start when the
  session becomes available.

Snooze and break countdowns always use wall-clock time.

## Startup, Quit, and relaunch

The application starts automatically at graphical login. **Quit** keeps it
stopped for the current login. Relaunch it from GNOME Applications or run:

```bash
systemctl --user start stand-up-reminder.service
```

## Uninstall

```bash
scripts/uninstall.sh
```

This stops the service and removes the installed application, launcher,
autostart entry, service file, and icons from user directories.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Short durations can be supplied with `STAND_UP_REMINDER_WORK_SECONDS`,
`STAND_UP_REMINDER_BREAK_SECONDS`, and
`STAND_UP_REMINDER_SNOOZE_SECONDS`.

## License

Stand Up Reminder is available under the [MIT License](LICENSE).
```

- [ ] **Step 7: Verify GREEN and the full suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_publication_docs -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Expected: 4 focused tests and the complete suite pass. The two existing settings fallback diagnostics are expected.

- [ ] **Step 8: Commit the publication-ready tree**

```bash
git add .gitignore LICENSE CHANGELOG.md README.md \
  tests/test_publication_docs.py
git commit -m "docs: prepare public Ubuntu release"
```

---

### Task 2: Validate and rewrite unpublished email metadata

**Files:**
- No tracked file changes.
- Create local ref: `refs/backup/pre-publication`
- Create bundle: `/tmp/stand-up-reminder-pre-publication.bundle`

**Interfaces:**
- Consumes: clean `master` from Task 1 and authenticated GitHub account `abszar`.
- Produces: content-identical `master` whose author/committer emails all use the canonical GitHub noreply address, plus two verified recovery points.

- [ ] **Step 1: Confirm preconditions**

```bash
test -z "$(git status --porcelain)"
test -z "$(git remote)"
gh auth status
if gh repo view abszar/stand-up-reminder >/dev/null 2>&1; then
  echo "Repository already exists; stop before rewriting."
  exit 1
fi
```

Expected: clean tree, no remote, active `abszar` login, and repository absent.

- [ ] **Step 2: Run tests, compilation, and diff validation**

```bash
publication_cache=$(mktemp -d /tmp/stand-up-reminder-publication.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX="$publication_cache" \
  python3 -m compileall -q stand_up_reminder tests
git diff --check
```

Expected: tests pass; compilation and diff checks exit zero without output.

- [ ] **Step 3: Scan tree and history for common secrets**

```bash
secret_pattern='ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|password[[:space:]]*[:=][[:space:]]*[^[:space:]]+|secret[[:space:]]*[:=][[:space:]]*[^[:space:]]+|token[[:space:]]*[:=][[:space:]]*[^[:space:]]+'

if git grep -nEI "$secret_pattern" -- .; then
  echo "Potential secret found in current tree; stop publication."
  exit 1
fi

secret_scan_file=$(mktemp /tmp/stand-up-reminder-secret-scan.XXXXXX)
git rev-list --all | while read -r commit; do
  git grep -nEI "$secret_pattern" "$commit" -- . || true
done > "$secret_scan_file"
test ! -s "$secret_scan_file"
```

Expected: no matches in current or historical content.

- [ ] **Step 4: Resolve noreply address and create recovery points**

```bash
github_login=$(gh api user --jq '.login')
github_id=$(gh api user --jq '.id')
test "$github_login" = "abszar"
public_noreply_email="${github_id}+abszar@users.noreply.github.com"
printf '%s\n' "$public_noreply_email"

git update-ref refs/backup/pre-publication HEAD
git bundle create /tmp/stand-up-reminder-pre-publication.bundle master
git bundle verify /tmp/stand-up-reminder-pre-publication.bundle
test "$(git rev-parse refs/backup/pre-publication)" = \
  "$(git rev-parse master)"
```

Expected: canonical address is printed; bundle and backup ref verify.

- [ ] **Step 5: Rewrite only matching author/committer emails**

Run in one shell:

```bash
github_id=$(gh api user --jq '.id')
export STAND_UP_NOREPLY_EMAIL="${github_id}+abszar@users.noreply.github.com"
export STAND_UP_PREVIOUS_EMAIL="<email-to-rewrite>"
export FILTER_BRANCH_SQUELCH_WARNING=1

git filter-branch -f --env-filter '
if [ "$GIT_AUTHOR_EMAIL" = "$STAND_UP_PREVIOUS_EMAIL" ]; then
  GIT_AUTHOR_EMAIL="$STAND_UP_NOREPLY_EMAIL"
  export GIT_AUTHOR_EMAIL
fi
if [ "$GIT_COMMITTER_EMAIL" = "$STAND_UP_PREVIOUS_EMAIL" ]; then
  GIT_COMMITTER_EMAIL="$STAND_UP_NOREPLY_EMAIL"
  export GIT_COMMITTER_EMAIL
fi
' -- master

git config user.email "$STAND_UP_NOREPLY_EMAIL"
unset STAND_UP_NOREPLY_EMAIL STAND_UP_PREVIOUS_EMAIL
unset FILTER_BRANCH_SQUELCH_WARNING
```

Expected: `master` rewrites successfully; backup ref and bundle retain original history.

- [ ] **Step 6: Verify rewrite invariants**

```bash
github_id=$(gh api user --jq '.id')
public_noreply_email="${github_id}+abszar@users.noreply.github.com"

test "$(git rev-parse master^{tree})" = \
  "$(git rev-parse refs/backup/pre-publication^{tree})"
test "$(git rev-list --count master)" = \
  "$(git rev-list --count refs/backup/pre-publication)"
test "$(git log --format='%ae%n%ce' master | sort -u)" = \
  "$public_noreply_email"
test "$(git config user.email)" = "$public_noreply_email"
test -z "$(git status --porcelain)"
git log -5 --format='%h %an <%ae> %s'
```

Expected: tree and commit counts match backup; only noreply email appears; tree is clean.

---

### Task 3: Create and verify the public GitHub repository

**Files:**
- No tracked file changes.
- Add remote: `origin` → `https://github.com/abszar/stand-up-reminder.git`

**Interfaces:**
- Consumes: privacy-safe local `master` from Task 2.
- Produces: public repository, pushed `master`, upstream tracking, exact description/topics/default branch.

- [ ] **Step 1: Reconfirm repository absence**

```bash
if gh repo view abszar/stand-up-reminder >/dev/null 2>&1; then
  echo "Repository now exists; stop and inspect before any write."
  exit 1
fi
```

Expected: lookup fails.

- [ ] **Step 2: Create the empty public repository**

```bash
gh repo create abszar/stand-up-reminder \
  --public \
  --description "A native Ubuntu Linux break reminder for GNOME that encourages two-minute standing breaks every 30 minutes."
```

Expected: GitHub returns the new URL. On failure, stop before remote/tag/release changes.

- [ ] **Step 3: Add origin and push master**

```bash
git remote add origin https://github.com/abszar/stand-up-reminder.git
git push -u origin master
```

Expected: `master` tracks `origin/master`. On push failure, retain repo/remote and do not release.

- [ ] **Step 4: Set exact metadata**

```bash
gh repo edit abszar/stand-up-reminder \
  --description "A native Ubuntu Linux break reminder for GNOME that encourages two-minute standing breaks every 30 minutes." \
  --default-branch master \
  --add-topic ubuntu \
  --add-topic linux \
  --add-topic gnome \
  --add-topic gtk \
  --add-topic python \
  --add-topic productivity \
  --add-topic break-reminder
```

Expected: command exits zero.

- [ ] **Step 5: Verify public repository state**

```bash
local_head=$(git rev-parse HEAD)
remote_head=$(git ls-remote origin refs/heads/master | cut -f1)
test "$local_head" = "$remote_head"
test "$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}')" = \
  "origin/master"

gh repo view abszar/stand-up-reminder \
  --json nameWithOwner,url,visibility,defaultBranchRef,description,repositoryTopics \
  --jq '{nameWithOwner,url,visibility,defaultBranch:.defaultBranchRef.name,description,topics:[.repositoryTopics[].name]|sort}'
```

Expected: heads match; visibility `PUBLIC`; default `master`; exact description and seven sorted topics.

---

### Task 4: Publish v1.0.0, reinstall, and verify

**Files:**
- No tracked file changes.
- Create annotated tag: `v1.0.0`
- Create GitHub release: `Stand Up Reminder v1.0.0`

**Interfaces:**
- Consumes: verified `origin/master` from Task 3.
- Produces: pushed tag, published source-only release, reinstalled running application, final URLs.

- [ ] **Step 1: Run fresh release-candidate verification**

```bash
release_cache=$(mktemp -d /tmp/stand-up-reminder-release.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX="$release_cache" \
  python3 -m compileall -q stand_up_reminder tests
git diff --check
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = \
  "$(git ls-remote origin refs/heads/master | cut -f1)"
```

Expected: tests pass; compilation/diff/tree are clean; local and remote heads match.

- [ ] **Step 2: Create and push annotated tag**

```bash
test -z "$(git tag --list v1.0.0)"
git tag -a v1.0.0 -m "Stand Up Reminder v1.0.0"
git push origin v1.0.0
```

Expected: annotated tag is pushed. On push failure, do not create release.

- [ ] **Step 3: Publish exact release notes**

```bash
gh release create v1.0.0 \
  --repo abszar/stand-up-reminder \
  --verify-tag \
  --title "Stand Up Reminder v1.0.0" \
  --notes-file - <<'RELEASE_NOTES'
Stand Up Reminder v1.0.0 is the first stable public release of the native
Ubuntu Linux standing-break reminder for GNOME.

## Highlights

- A 30-minute work cycle followed by a two-minute standing break.
- Repeatable **Give me 5 minutes** snoozing with a fresh break countdown.
- **Skip this break** support that immediately starts a new work interval.
- Explicit return confirmation after a completed break.
- Active-time and wall-clock modes for lock and suspend behavior.
- GNOME top-bar integration, Applications menu launcher, and login startup.

## Requirements

Tested on Ubuntu 24.04 LTS with GNOME Shell 46 and X11. The application uses
Python 3, GTK 3, PyGObject, and Ayatana AppIndicator.

## Install

```bash
git clone https://github.com/abszar/stand-up-reminder.git
cd stand-up-reminder
scripts/install.sh
```

See the [README](https://github.com/abszar/stand-up-reminder#install-on-ubuntu)
for dependencies, verification, updating, and uninstalling.
RELEASE_NOTES
```

Expected: published, non-draft, non-prerelease release with generated source archives only.

- [ ] **Step 4: Reinstall and verify the local application**

```bash
scripts/install.sh

install_root="$HOME/.local/share/stand-up-reminder/stand_up_reminder"
for source_file in stand_up_reminder/*.py; do
  cmp --silent "$source_file" \
    "$install_root/$(basename "$source_file")" || exit 1
done

test "$(systemctl --user is-active stand-up-reminder.service)" = "active"
systemctl --user show stand-up-reminder.service \
  -p ActiveState -p SubState -p MainPID --no-pager
```

Expected: installed files match; service is active/running with nonzero PID.

- [ ] **Step 5: Verify tag, release, and final handoff**

```bash
test "$(git rev-parse 'v1.0.0^{}')" = "$(git rev-parse HEAD)"
remote_tag_commit=$(git ls-remote origin 'refs/tags/v1.0.0^{}' | cut -f1)
test "$remote_tag_commit" = "$(git rev-parse HEAD)"

gh release view v1.0.0 \
  --repo abszar/stand-up-reminder \
  --json name,tagName,url,isDraft,isPrerelease,targetCommitish \
  --jq '{name,tagName,url,isDraft,isPrerelease,targetCommitish}'

gh repo view abszar/stand-up-reminder \
  --json url,visibility,defaultBranchRef,description,repositoryTopics
git status --short --branch
```

Expected: local/remote tag dereference to `HEAD`; exact published release; public repository on `master`; clean tree tracking `origin/master`.
