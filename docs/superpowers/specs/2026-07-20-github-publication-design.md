# GitHub Publication and v1.0.0 Release Design

## Goal

Publish Stand Up Reminder as a polished public GitHub repository under the
authenticated `abszar` account, provide a complete Ubuntu Linux installation
guide, and create the first stable `v1.0.0` release.

## Repository identity

- Repository: `abszar/stand-up-reminder`
- Visibility: public
- Default branch: `master`, matching the existing local branch
- Description: `A native Ubuntu Linux break reminder for GNOME that encourages two-minute standing breaks every 30 minutes.`
- Topics: `ubuntu`, `linux`, `gnome`, `gtk`, `python`, `productivity`, and
  `break-reminder`
- License: MIT

The repository will preserve the existing development history. Because it has
not been published, every author and committer email in that history will be
rewritten from the current public email address to the authenticated GitHub
account's private noreply address before the first push. A local backup ref
will be created before rewriting so the original history remains recoverable.
Names, commit messages, timestamps, and file contents will otherwise remain
unchanged.

## Public repository contents

The existing application source, tests, installed assets, development plans,
and specifications remain tracked. The publication work adds:

- an MIT `LICENSE` file naming Abdelali Bourassine as the copyright holder;
- a `.gitignore` covering Python bytecode, virtual environments, coverage
  output, editor metadata, and common build artifacts;
- a concise `CHANGELOG.md` with a `1.0.0` entry dated 2026-07-20;
- an expanded `README.md` that serves as the public project landing page and
  local installation guide.

No binary package or custom release archive will be added. GitHub's automatic
source `.zip` and `.tar.gz` archives are sufficient for this script-installed
Python/GTK application.

## README structure

The README will cover:

1. A short Ubuntu Linux/GNOME description and feature summary.
2. Compatibility: tested on Ubuntu 24.04, GNOME Shell 46, and X11.
3. Required Ubuntu packages:
   - `python3`
   - `python3-gi`
   - `gir1.2-gtk-3.0`
   - `gir1.2-ayatanaappindicator3-0.1`
   - `gnome-shell-extension-appindicator`
   - `desktop-file-utils`
4. Installation using `git clone`, entering the checkout, and running
   `scripts/install.sh`.
5. Verification using `systemctl --user status stand-up-reminder.service`.
6. Updating using `git pull` followed by `scripts/install.sh`.
7. Controls, snooze/skip behavior, timing modes, startup, Quit, and relaunch.
8. Uninstallation using `scripts/uninstall.sh`.
9. Development tests using `python3 -m unittest discover -s tests -v`.
10. MIT license attribution and a link to `LICENSE`.

The guide will state that other Ubuntu releases or desktop environments are
not currently verified rather than claiming unsupported compatibility.

## Pre-publication validation

Before any GitHub write operation:

- confirm the working tree is clean;
- run the complete unit-test suite;
- run Python bytecode compilation and `git diff --check`;
- scan the current tree and full Git history for common credential and private
  key patterns;
- confirm that the intended GitHub repository still does not exist;
- retrieve the authenticated account ID and construct its canonical
  `ID+abszar@users.noreply.github.com` address;
- create and verify a local backup ref before rewriting commit metadata;
- confirm every rewritten commit uses the noreply address and the working tree
  matches the pre-rewrite tree.

If validation or history rewriting fails, publication stops before repository
creation. The original history can be recovered from the backup ref.

## GitHub publication flow

After local validation and metadata rewriting:

1. Create `abszar/stand-up-reminder` as a public repository without generating
   a README, license, or `.gitignore` on GitHub.
2. Add it as the local `origin` remote and push `master`, setting upstream
   tracking.
3. Set the repository description and topics to the exact approved values.
4. Verify the repository is public and `master` is its default branch.

If repository creation succeeds but pushing fails, do not create a release.
Report the repository state and retry only the failed safe operation. Never
force-push after the initial publication unless the user explicitly approves
it.

## v1.0.0 release

Create annotated tag `v1.0.0` on the final publication commit and push it.
Publish a GitHub release titled `Stand Up Reminder v1.0.0` with notes covering:

- the 30-minute work and two-minute standing-break cycle;
- repeatable five-minute snoozing and full-break skipping;
- completed-break return confirmation;
- active-time and wall-clock timing modes;
- Ubuntu GNOME top-bar integration and login startup;
- tested platform and package requirements;
- installation link and commands.

The release will use GitHub-generated source archives only and will not be
marked as a draft or prerelease.

## Post-publication verification

Verify through GitHub CLI/API that:

- the repository URL is reachable and visibility is public;
- `origin` points to the new repository and `master` tracks `origin/master`;
- the remote head matches the local publication commit;
- description and topics match the approved values;
- the `v1.0.0` tag resolves to the intended commit;
- the release is published, non-draft, non-prerelease, and linked to `v1.0.0`;
- the clone URL and release URL are available for handoff.

## Ongoing update workflow

The existing repository instruction remains authoritative: after application
code or installed assets change, run `scripts/install.sh`, confirm the
installed package matches the repository, and verify that
`stand-up-reminder.service` is active and running. Public GitHub updates are
then pushed only after tests and installation verification succeed.

## Out of scope

- Debian packages, PPAs, Flatpak, Snap, or AppImage distribution.
- GitHub Actions or automated release publishing.
- Binary release assets or cryptographic checksum files.
- Compatibility guarantees beyond the tested Ubuntu 24.04 GNOME/X11 system.
- A project website, screenshots, issue templates, or contribution guide.
