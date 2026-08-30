"""The eye breaks: which prompt is owed, when, and what it is doing.

Screen work strains the eyes on a clock of its own — the blink rate falls
and the focusing muscle holds one distance for as long as the screen does —
so this runs beside the standing cycle rather than inside it. Everything
here is pure: the rotation, the timing, and the frame each prompt is on at
a given moment, so the whole schedule can be tested without a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .i18n import _


# A card is twenty seconds because it exists to serve the twenty-twenty-twenty
# rule, and the interval it runs on is the twenty in the middle.
CARD_SECONDS = 20
INTERVAL_PRESETS = (15 * 60, 20 * 60, 30 * 60)
DEFAULT_INTERVAL_SECONDS = 20 * 60


@dataclass(frozen=True)
class Prompt:
    """One thing a card can ask for, and the clothes it asks in."""

    key: str
    title: str
    subtitle: str
    setting_label: str
    accent: str
    body: str


LOOK_FAR = Prompt(
    "far",
    _("LOOK FAR"),
    _("SOMETHING 6 METRES OFF"),
    _("Look out a window"),
    "sky",
    "slate",
)
CLOSE_EYES = Prompt(
    "shut",
    _("CLOSE YOUR EYES"),
    _("CLOSE"),
    _("Close your eyes"),
    "plum",
    "void",
)
MOVE_EYES = Prompt(
    "move",
    _("MOVE YOUR EYES"),
    _("FOLLOW THE LIT DOT"),
    _("Move your eyes"),
    "mint",
    "ink",
)

PROMPTS = (LOOK_FAR, CLOSE_EYES, MOVE_EYES)
BY_KEY = {prompt.key: prompt for prompt in PROMPTS}

# Looking into the distance is the part with the clearest reason behind it,
# so it takes four turns of the six. Moving the eyes has the thinnest, so it
# takes one.
ROTATION = ("far", "far", "shut", "far", "far", "move")


def next_prompt(index: int, muted) -> Optional[tuple]:
    """The next prompt due from this point in the rotation, and where to go on.

    A muted prompt is stepped over rather than shown as a gap, so muting one
    leaves the others coming round at the same rate. Muting all of them ends
    the feature without needing a second switch for it.
    """
    for step in range(len(ROTATION)):
        at = (index + step) % len(ROTATION)
        key = ROTATION[at]
        if key not in muted:
            return BY_KEY[key], (at + 1) % len(ROTATION)
    return None


def eye_due(previous: int, current: int, interval: int) -> bool:
    """Whether a card falls due as the clock passes from one reading to the next.

    Counted in whole intervals rather than exact instants so that a late tick,
    or a laptop coming back from suspend, still fires the card it stepped over
    instead of silently skipping it.
    """
    if current <= previous or interval <= 0:
        return False
    return current // interval > previous // interval


# --- the closed-eye card ---------------------------------------------------
# A shut eye has two states doing different work. A firm squeeze presses the
# lid glands that incomplete screen-blinking leaves unexpressed; a resting
# close lets the tear film spread. Three squeezes, then rest: holding a
# squeeze for the whole twenty seconds only tires the lids.
SQUEEZE_BEATS = (700, 2700, 4700)
SQUEEZE_HOLD = 1400
CLOSE_MS = 700
SQUEEZE_END = 6700
OPEN_AT = 19300


@dataclass(frozen=True)
class ShutFrame:
    lid: float
    tight: bool
    phase: str
    pips: int


def shut_frame(ms: int) -> ShutFrame:
    """Where the closed-eye card is in its twenty seconds."""
    if ms < CLOSE_MS:
        return ShutFrame(max(0.0, ms / CLOSE_MS), False, _("CLOSE"), 0)
    if ms < SQUEEZE_END:
        since = ms - CLOSE_MS
        tight = (since % 2000) < SQUEEZE_HOLD
        pips = min(3, since // 2000 + 1 if tight else -(-since // 2000))
        return ShutFrame(1.0, tight, _("SQUEEZE") if tight else _("LET GO"), pips)
    if ms < OPEN_AT:
        return ShutFrame(1.0, False, _("REST"), 3)
    opening = (ms - OPEN_AT) / (CARD_SECONDS * 1000 - OPEN_AT)
    return ShutFrame(max(0.0, 1.0 - opening), False, _("OPEN"), 3)


# --- the moving-eye card ---------------------------------------------------
# The eyes sit at the middle of the ring they are asked to look around, so
# one table gives both the pupil offset and, by its sign, which corner of the
# ring the lit station belongs to.
GAZE = {
    "C": (0, 0),
    "W": (-3, 0),
    "E": (3, 0),
    "N": (0, -2),
    "S": (0, 2),
    "NW": (-3, -2),
    "NE": (3, -2),
    "SE": (3, 2),
    "SW": (-3, 2),
}
STATIONS = ("W", "E", "N", "S", "NW", "NE", "SE", "SW")
SEQUENCE = (
    "C", "W", "E", "N", "S", "C",
    "NW", "N", "NE", "E", "SE", "S", "SW", "W",
)
STATION_MS = 800


def move_station(ms: int) -> str:
    """Which station the card is asking for at this moment."""
    return SEQUENCE[(ms // STATION_MS) % len(SEQUENCE)]


# --- the window card -------------------------------------------------------
CLOUD_MS = 400
CLOUD_SPAN = 40
SUN_MS = 500
BIRD_MS = 6000


def cloud_offset(ms: int, direction: int) -> int:
    """A cloud's left edge, drifting one art pixel at a time and wrapping."""
    steps = direction * (ms // CLOUD_MS)
    return (steps % CLOUD_SPAN + CLOUD_SPAN) % CLOUD_SPAN - 4


def sun_lit(ms: int) -> bool:
    """The sun alternates amber and bone on a half-second, never in between."""
    return (ms // SUN_MS) % 2 == 0


def bird_x(ms: int) -> Optional[int]:
    """Where the bird is, or nothing for the half of the cycle it is away."""
    through = (ms % BIRD_MS) / BIRD_MS
    if through >= 0.5:
        return None
    return int(through * 2 * 36) - 2
