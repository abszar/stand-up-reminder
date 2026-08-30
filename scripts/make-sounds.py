#!/usr/bin/env python3
"""Generate the application's chiptune cues into data/sounds.

The picture is flat colour on a grid with no easing, so the sound is its
equivalent: two or three notes, one waveform, a hard envelope. Anything with
a tail on it would belong to a different application.

Run after changing a cue; the resulting WAV files are checked in so that no
synthesis happens at runtime.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

RATE = 44_100
EDGE = 0.004  # seconds of ramp at each end, enough to kill the click

# name -> (waveform, peak amplitude, [(hertz, milliseconds), ...])
CUES = {
    "eye-look-far": ("square", 0.09, [(523.25, 70), (659.25, 70), (783.99, 70), (1046.50, 120)]),
    "eye-close": ("triangle", 0.12, [(392.00, 180), (293.66, 260)]),
    "eye-move": ("square", 0.07, [(440.00, 80), (587.33, 120)]),
    "eye-squeeze": ("square", 0.05, [(659.25, 70)]),
    "eye-done": ("square", 0.07, [(783.99, 60), (1046.50, 100)]),
}


def wave_at(kind: str, phase: float) -> float:
    """One sample of the named waveform at a phase in [0, 1)."""
    if kind == "square":
        return 1.0 if phase < 0.5 else -1.0
    if kind == "triangle":
        return 4.0 * abs(phase - 0.5) - 1.0
    raise ValueError(f"unknown waveform: {kind}")


def note(kind: str, peak: float, hertz: float, ms: int) -> list:
    total = int(RATE * ms / 1000)
    ramp = max(1, int(RATE * EDGE))
    samples = []
    for index in range(total):
        phase = (index * hertz / RATE) % 1.0
        gain = peak
        if index < ramp:
            gain *= index / ramp
        elif index > total - ramp:
            gain *= max(0.0, (total - index) / ramp)
        samples.append(wave_at(kind, phase) * gain)
    return samples


def write(path: Path, samples: list) -> None:
    frames = b"".join(
        struct.pack("<h", max(-32768, min(32767, int(value * 32767))))
        for value in samples
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "data" / "sounds"
    out.mkdir(parents=True, exist_ok=True)
    for name, (kind, peak, notes) in CUES.items():
        samples = []
        for hertz, ms in notes:
            samples.extend(note(kind, peak, hertz, ms))
        path = out / f"{name}.wav"
        write(path, samples)
        print(f"{path.name}  {len(samples) / RATE:.2f}s  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
