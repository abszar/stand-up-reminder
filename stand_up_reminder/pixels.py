"""The pixel world: palette, art-grid maths, and the shipped sprite sheets.

Everything the interface draws comes from here. The module keeps the pure
art-grid logic — cell counts, score bands, mark placement — free of GTK so
that it can be tested on its own, and loads the sprite PNGs lazily as alpha
masks that are painted in whichever palette colour the state calls for.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Sequence

import cairo

import gi

gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf


# One art pixel is four real pixels; every dimension in the design is a whole
# number of art pixels.
ART = 4

PALETTE = {
    "void": "#100c1a",
    "ink": "#1a1524",
    "slate": "#2e2740",
    "edge": "#4a3f66",
    "bone": "#f2ece0",
    "mist": "#9a8fb5",
    "amber": "#ffb03a",
    "coral": "#ff5f5f",
    "mint": "#6fe0a8",
    "sky": "#5fc8ff",
    "plum": "#7a4fd6",
}

# Shades used by pressed and hovered controls, taken from the design's own
# button states rather than computed, so they stay flat colours.
AMBER_HOVER = "#ffd08a"
AMBER_PRESSED = "#e09420"
PRESSED_FILL = "#231d33"

# One mark colour per recorded outcome.
MARK_COLORS = {
    "taken": PALETTE["mint"],
    "away": PALETTE["sky"],
    "missed": PALETTE["coral"],
    "skipped": PALETTE["edge"],
    "snoozed": PALETTE["plum"],
}

# The contribution grid: an empty tile and four steps towards mint, flattened
# to hard hexes so that no tile is ever drawn with alpha.
HEAT_SHADES = ("#255c45", "#3d8f68", "#56c08c", "#6fe0a8")

PROGRESS_CELLS = 27
URGENT_CELLS = 5

# The card is revealed in six bands from the centre out.
WIPE_ORDER = (2, 3, 1, 4, 0, 5)


def ap(art_pixels: float) -> int:
    """Real pixels for a length given in art pixels."""
    return int(round(art_pixels * ART))


def rgb(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


def filled_cells(
    remaining: float, total: float, cells: int = PROGRESS_CELLS
) -> int:
    """Lit cells of the progress bar, which only ever changes a cell at a time."""
    if total <= 0:
        return 0
    fraction = max(0.0, min(1.0, float(remaining) / float(total)))
    return int(fraction * cells)


def cells_urgent(filled: int) -> bool:
    """True once so few cells remain that the whole bar turns coral."""
    return filled < URGENT_CELLS


def band_color(percent: Optional[int]) -> str:
    """Score colour: mint from 70, amber from 40, coral below."""
    if percent is None:
        return PALETTE["mist"]
    if percent >= 70:
        return PALETTE["mint"]
    if percent >= 40:
        return PALETTE["amber"]
    return PALETTE["coral"]


def mood_glyph(percent: Optional[int]) -> str:
    """Which mood sprite stands for this score."""
    if percent is None:
        return "flat"
    if percent >= 85:
        return "spark"
    if percent >= 70:
        return "up"
    if percent >= 50:
        return "flat"
    return "down"


def face_expression(percent: Optional[int]) -> str:
    """The verdict the face wears on the score screen."""
    if percent is None:
        return "rest"
    if percent >= 85:
        return "grin1"
    if percent >= 50:
        return "rest"
    return "flat"


def pill_rows(seconds: int) -> tuple[str, ...]:
    """Stacked pill rows: minutes over seconds, gaining an hours row on top."""
    seconds = max(0, int(seconds))
    seconds = min(seconds, 10 * 3600 - 1)
    hours, remainder = divmod(seconds, 3600)
    minutes, second = divmod(remainder, 60)
    rows = (f"{minutes:02d}", f"{second:02d}")
    if hours:
        return (f"{hours:02d}",) + rows
    return rows


def pill_height(rows: Sequence[str]) -> int:
    """Pill height in real pixels; the hours row opens it downward by 10 ap."""
    return ap(39 if len(rows) < 3 else 49)


def timeline_marks(
    points: Iterable[tuple[float, str]],
    track_ap: int,
    mark_ap: int = 2,
    min_gap_ap: int = 3,
) -> list[tuple[int, str]]:
    """Mark positions along the day track, snapped to the art grid.

    Two marks closer together than the minimum gap merge into one, carrying
    the later outcome's colour so that the most recent verdict is the one on
    show.
    """
    travel = max(0, track_ap - mark_ap)
    marks: list[tuple[int, str]] = []
    for fraction, outcome in points:
        if outcome not in MARK_COLORS:
            continue
        at = int(round(min(1.0, max(0.0, fraction)) * travel))
        if marks and at - marks[-1][0] < min_gap_ap:
            marks[-1] = (marks[-1][0], outcome)
            continue
        marks.append((at, outcome))
    return marks


def heat_hex(level: Optional[int]) -> str:
    """Tile colour for a day of the contribution grid."""
    if level is None:
        return PALETTE["slate"]
    return HEAT_SHADES[max(0, min(len(HEAT_SHADES) - 1, level))]


# The contribution grid, in art pixels: a label column, then square tiles.
HEAT_TILE = 8
HEAT_GUTTER = 2
HEAT_LABELS = 16
HEAT_ROWS = 7


def heat_grid_size(columns: int) -> tuple[int, int]:
    """Real size of a grid of this many weeks."""
    width = HEAT_LABELS + HEAT_GUTTER + columns * HEAT_TILE
    width += max(0, columns - 1) * HEAT_GUTTER
    height = HEAT_ROWS * HEAT_TILE + (HEAT_ROWS - 1) * HEAT_GUTTER
    return ap(width), ap(height)


def heat_tile_at(x: float, y: float, columns: int) -> Optional[tuple[int, int]]:
    """Grid position under a point, or None for labels, gutters and margins."""
    step = ap(HEAT_TILE + HEAT_GUTTER)
    left = x - ap(HEAT_LABELS + HEAT_GUTTER)
    if left < 0 or y < 0:
        return None
    column, within_column = divmod(left, step)
    row, within_row = divmod(y, step)
    if not 0 <= column < columns or not 0 <= row < HEAT_ROWS:
        return None
    if within_column >= ap(HEAT_TILE) or within_row >= ap(HEAT_TILE):
        return None
    return int(column), int(row)


def sprite_dir() -> Path:
    """Where the shipped sprites live, in an installed copy or in the tree."""
    override = os.environ.get("STAND_UP_REMINDER_SPRITES")
    if override:
        return Path(override)
    package = Path(__file__).resolve().parent
    installed = package.parent / "sprites"
    if installed.is_dir():
        return installed
    return package.parent / "data" / "sprites"


# Sheets are authored one image pixel per art pixel, frames left to right with
# a one pixel gutter: name -> (file, frame width, frame count).
SHEETS = {
    "digits-big": ("digits-big-sheet.png", 6, 10),
    "digits-small": ("digits-small-sheet.png", 4, 10),
    "face": ("face-sheet.png", 16, 8),
    "face-disc": ("face-disc-mask.png", 16, 8),
    "face-bob": ("face-bob-sheet.png", 8, 2),
    "burst": ("confirm-burst-sheet.png", 12, 5),
}

SINGLES = {
    "colon-big": "digit-big-colon.png",
    "colon-small": "digit-small-colon.png",
    "mood-spark-1": "mood-spark-f1.png",
    "mood-spark-2": "mood-spark-f2.png",
    "mood-up": "mood-up.png",
    "mood-flat": "mood-flat.png",
    "mood-down": "mood-down.png",
    "checkbox-on": "checkbox-on.png",
    "checkbox-off": "checkbox-off.png",
}

FACE_FRAMES = ("rest", "blink", "alert", "yawn", "grin1", "grin2", "sleep", "flat")

# The features are the ink-coloured pixels of the face sheets; the disc is
# everything the silhouette covers, so each is painted in its own colour.
_INK_PIXEL = (0x1A, 0x15, 0x24)


class Mask:
    """One sprite frame as an alpha mask, ready to be painted in any colour."""

    def __init__(self, surface: cairo.ImageSurface, width: int, height: int) -> None:
        self.surface = surface
        self.width = width
        self.height = height


def _mask_from_pixels(
    pixels: Sequence[int],
    rowstride: int,
    channels: int,
    left: int,
    top: int,
    width: int,
    height: int,
    keep,
) -> Mask:
    surface = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
    stride = surface.get_stride()
    data = surface.get_data()
    for y in range(height):
        base = (top + y) * rowstride + left * channels
        for x in range(width):
            offset = base + x * channels
            red, green, blue = pixels[offset], pixels[offset + 1], pixels[offset + 2]
            alpha = pixels[offset + 3] if channels == 4 else 255
            data[y * stride + x] = 255 if alpha > 127 and keep(red, green, blue) else 0
    surface.mark_dirty()
    return Mask(surface, width, height)


class Sprites:
    """Lazily loaded sprite masks, cached by name and frame."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory) if directory else sprite_dir()
        self._masks: dict[tuple[str, int], Mask] = {}
        self._missing: set[str] = set()

    def _pixbuf(self, filename: str):
        path = self.directory / filename
        return GdkPixbuf.Pixbuf.new_from_file(str(path))

    def _slice(self, name: str, frame: int) -> Optional[Mask]:
        keep = lambda *_channels: True
        if name in SHEETS:
            filename, frame_width, count = SHEETS[name]
            frame = max(0, min(count - 1, frame))
            left = frame * (frame_width + 1)
            width = frame_width
        elif name in SINGLES:
            filename, left, width = SINGLES[name], 0, None
        elif name.endswith("-features"):
            base = name[: -len("-features")]
            filename, frame_width, count = SHEETS[base]
            frame = max(0, min(count - 1, frame))
            left, width = frame * (frame_width + 1), frame_width
            keep = lambda r, g, b: (r, g, b) == _INK_PIXEL
        elif name.endswith("-disc"):
            base = name[: -len("-disc")]
            filename, frame_width, count = SHEETS[base]
            frame = max(0, min(count - 1, frame))
            left, width = frame * (frame_width + 1), frame_width
            keep = lambda r, g, b: (r, g, b) != _INK_PIXEL
        else:
            return None
        pixbuf = self._pixbuf(filename)
        channels = pixbuf.get_n_channels()
        if width is None:
            width = pixbuf.get_width()
        return _mask_from_pixels(
            pixbuf.get_pixels(),
            pixbuf.get_rowstride(),
            channels,
            left,
            0,
            width,
            pixbuf.get_height(),
            keep,
        )

    def mask(self, name: str, frame: int = 0) -> Optional[Mask]:
        key = (name, frame)
        if key in self._masks:
            return self._masks[key]
        if name in self._missing:
            return None
        try:
            loaded = self._slice(name, frame)
        except Exception:  # pragma: no cover - a missing asset must not crash
            self._missing.add(name)
            return None
        if loaded is None:
            self._missing.add(name)
            return None
        self._masks[key] = loaded
        return loaded

    def paint(
        self,
        context: cairo.Context,
        name: str,
        x: int,
        y: int,
        scale: int,
        color: str,
        frame: int = 0,
    ) -> int:
        """Blit one sprite in a flat colour; returns the width drawn."""
        mask = self.mask(name, frame)
        if mask is None:
            return 0
        context.save()
        context.translate(x, y)
        context.scale(scale, scale)
        context.set_source_rgb(*rgb(color))
        pattern = cairo.SurfacePattern(mask.surface)
        pattern.set_filter(cairo.FILTER_NEAREST)
        context.mask(pattern)
        context.restore()
        return mask.width * scale

    def face(
        self,
        context: cairo.Context,
        x: int,
        y: int,
        scale: int,
        disc_color: str,
        expression: str = "rest",
        sheet: str = "face",
    ) -> None:
        """The character: a coloured disc with its features knocked out in ink."""
        frame = FACE_FRAMES.index(expression) if expression in FACE_FRAMES else 0
        disc = "face-disc" if sheet == "face" else f"{sheet}-disc"
        self.paint(context, disc, x, y, scale, disc_color, frame)
        self.paint(context, f"{sheet}-features", x, y, scale, PALETTE["ink"], frame)

    def digits(
        self,
        context: cairo.Context,
        text: str,
        x: int,
        y: int,
        scale: int,
        color: str,
        big: bool = True,
    ) -> int:
        """Draw a run of sprite digits; the advance is one art pixel."""
        sheet = "digits-big" if big else "digits-small"
        colon = "colon-big" if big else "colon-small"
        glyph_width = SHEETS[sheet][1]
        cursor = x
        for character in text:
            if character.isdigit():
                self.paint(
                    context, sheet, cursor, y, scale, color, int(character)
                )
                cursor += (glyph_width + 1) * scale
            elif character == ":":
                self.paint(context, colon, cursor, y, scale, color)
                mask = self.mask(colon)
                cursor += ((mask.width if mask else 1) + 1) * scale
            else:  # a blanked colon keeps the digits from shifting as it blinks
                mask = self.mask(colon)
                cursor += ((mask.width if mask else 1) + 1) * scale
        return cursor - x

    def digits_width(self, text: str, scale: int, big: bool = True) -> int:
        sheet = "digits-big" if big else "digits-small"
        colon = "colon-big" if big else "colon-small"
        mask = self.mask(colon)
        colon_width = (mask.width if mask else 1) + 1
        glyph_width = SHEETS[sheet][1] + 1
        total = sum(
            glyph_width if character.isdigit() else colon_width
            for character in text
        )
        return total * scale
