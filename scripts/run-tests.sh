#!/bin/sh
set -eu

# Runs the test suite with the C locale pinned. The tests assert the
# untranslated strings, so a translated desktop session must not change the
# catalogue that the application binds at import time.

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

LANGUAGE=en
LC_ALL=C
LANG=C
export LANGUAGE LC_ALL LANG

exec python3 -m unittest discover "$@"
