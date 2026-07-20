from __future__ import annotations

import gettext
import os
from pathlib import Path


DOMAIN = "stand-up-reminder"


def locale_directory() -> Path:
    """Locate compiled catalogues, preferring the ones shipped with this copy.

    The application is installed under a user-local prefix, so the catalogues
    that belong to this installation are found relative to the package before
    any system-wide directory is considered.
    """
    override = os.environ.get("STAND_UP_REMINDER_LOCALE_DIR")
    if override:
        return Path(override)
    bundled = Path(__file__).resolve().parent.parent / "locale"
    if bundled.is_dir():
        return bundled
    return Path.home() / ".local" / "share" / "locale"


_translation = gettext.translation(
    DOMAIN, localedir=str(locale_directory()), fallback=True
)

gettext_ = _translation.gettext
ngettext = _translation.ngettext

# Short alias matching the conventional gettext spelling used at call sites.
_ = gettext_
