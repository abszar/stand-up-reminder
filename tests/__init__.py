"""Tests for Stand Up Reminder.

The user-visible strings asserted by these tests are the untranslated
originals, so the catalogue lookup is pinned to the C locale before the
application package binds its translation at import time.
"""

import os

os.environ["LANGUAGE"] = "en"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"
