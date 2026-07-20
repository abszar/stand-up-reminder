# Repository Instructions

- Don't EVER mention "Anthropic ..." in commit messages.
- After every update to application code or installed assets, run
  `scripts/install.sh` to replace the installed user-local copy and restart
  `stand-up-reminder.service`.
- Verify that the installed Python package matches the repository source and
  that `stand-up-reminder.service` is active and running.
