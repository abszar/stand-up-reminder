# Repository Instructions

- Don't EVER mention "Anthropic ..." in commit messages.
- Run the test suite with `scripts/run-tests.sh`, which pins the C locale so
  that assertions on untranslated strings hold on a translated desktop.
- After changing any user-visible string, run `scripts/update-translations.sh`
  and translate the new entries in `po/*.po`.
- After every update to application code or installed assets, run
  `scripts/install.sh` to replace the installed user-local copy and restart
  `stand-up-reminder.service`.
- Verify that the installed Python package matches the repository source and
  that `stand-up-reminder.service` is active and running.
