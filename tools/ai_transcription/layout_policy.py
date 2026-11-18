"""Shared two-voice drum notation policy inferred from reference scores."""

from __future__ import annotations


# The bass drum and pedal hi-hat form the lower voice.  Everything else that
# this converter currently supports belongs to the upper voice, including the
# snare and toms.  A simultaneous snare/cymbal hit therefore remains one chord.
UPPER_DRUMS = {
    39,
    37,
    38,
    40,
    41,
    42,
    43,
    45,
    46,
    47,
    48,
    49,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    57,
    59,
    60,
    61,
    62,
    63,
    64,
    65,
    66,
    67,
    68,
    69,
    70,
    71,
    72,
    73,
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    82,
    83,
    84,
    85,
    86,
    87,
}
LOWER_DRUMS = {35, 36, 44}


def voice_for_pitch(pitch: int) -> int:
    if pitch in UPPER_DRUMS:
        return 0
    if pitch in LOWER_DRUMS:
        return 1
    raise ValueError(f"Unsupported drum pitch {pitch}")
