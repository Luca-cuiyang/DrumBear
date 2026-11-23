#!/usr/bin/env python3
"""Build a two-voice DB Score/MuseScore drum score directly from event JSON.

MusicXML import in DB Score merges upper and lower drum voices and can move
events when a measure contains mixed subdivisions.  This writer emits the
native score structure instead, so each vertical onset remains an onset and
drum voices stay independent.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from layout_policy import LOWER_DRUMS, UPPER_DRUMS, voice_for_pitch


DRUMS = {
    35: ("Acoustic Bass Drum", "normal", 8, 1, 2, 14),
    36: ("Acoustic Bass Drum", "normal", 7, 1, 2, 14),
    37: ("Side Stick", "slashed1", 3, 0, 1, 19),
    38: ("Acoustic Snare", "normal", 3, 0, 1, 16),
    39: ("Hand Clap", "cross", 3, 0, 1, 16),
    40: ("Electric Snare", "slash", 3, 0, 1, 16),
    41: ("Low Floor Tom", "normal", 6, 0, 1, 14),
    42: ("Closed Hi-Hat", "cross", -1, 0, 1, 20),
    43: ("High Floor Tom", "normal", 5, 0, 1, 14),
    44: ("Pedal Hi-Hat", "cross", 9, 1, 2, 12),
    45: ("Low Tom", "normal", 4, 0, 1, 16),
    46: ("Open Hi-Hat", "xcircle", -1, 0, 1, 12),
    47: ("Low-Mid Tom", "normal", 2, 0, 1, 16),
    48: ("Hi-Mid Tom", "normal", 1, 0, 1, 18),
    49: ("Crash Cymbal 1", "cross", -2, 0, 1, 21),
    50: ("High Tom", "normal", 0, 0, 1, 18),
    51: ("Ride Cymbal", "cross", 0, 0, 1, 12),
    52: ("China Cymbal", "x", -3, 0, 1, 21),
    53: ("Ride Bell", "diamond", 0, 0, 1, 12),
    54: ("Tambourine", "diamond", 1, 0, 1, 12),
    55: ("Splash Cymbal", "cross", -4, 0, 1, 21),
    56: ("Cowbell", "triangle-down", 1, 0, 1, 12),
    57: ("Crash Cymbal 2", "cross", -3, 0, 1, 21),
    58: ("Vibraslap", "cross", 2, 0, 1, 18),
    59: ("Ride Cymbal 2", "cross", 2, 0, 1, 12),
    60: ("Hi Bongo", "normal", -1, 0, 1, 18),
    61: ("Low Bongo", "normal", -1, 0, 1, 16),
    62: ("Mute Hi Conga", "cross", 0, 0, 1, 18),
    63: ("Open Hi Conga", "circle", 0, 0, 1, 18),
    64: ("Low Conga", "normal", 2, 0, 1, 14),
    65: ("High Timbale", "normal", 1, 0, 1, 18),
    66: ("Low Timbale", "normal", 3, 0, 1, 16),
    67: ("High Agogo", "normal", -2, 0, 1, 18),
    68: ("Low Agogo", "normal", -1, 0, 1, 16),
    69: ("Cabasa", "cross", 1, 0, 1, 20),
    70: ("Maracas", "cross", -1, 0, 1, 20),
    71: ("Short Whistle", "normal", -1, 0, 1, 18),
    72: ("Long Whistle", "normal", -1, 0, 1, 18),
    73: ("Short Guiro", "normal", -1, 0, 1, 18),
    74: ("Long Guiro", "normal", -1, 0, 1, 18),
    75: ("Claves", "normal", -1, 0, 1, 18),
    76: ("Hi Wood Block", "normal", 0, 0, 1, 18),
    77: ("Low Wood Block", "normal", 2, 0, 1, 16),
    78: ("Mute Cuica", "normal", 0, 0, 1, 18),
    79: ("Open Cuica", "normal", 0, 0, 1, 18),
    80: ("Mute Triangle", "triangle-up", 0, 0, 1, 18),
    81: ("Open Triangle", "triangle-up", 0, 0, 1, 18),
    82: ("Shaker", "cross", 0, 0, 1, 18),
    83: ("Jingle Bell", "normal", 0, 0, 1, 18),
    84: ("Bell Tree", "normal", 0, 0, 1, 18),
    85: ("Castanets", "normal", 0, 0, 1, 18),
    86: ("Mute Surdo", "normal", 8, 1, 2, 14),
    87: ("Open Surdo", "normal", 8, 1, 2, 14),
}

ARTICULATION_SUBTYPES = {
    "accent": "articAccentAbove",
    "tenuto": "articTenutoAbove",
}

UNWANTED_DRUM_ARTICULATIONS = {"staccato", "staccatissimo"}

DURATIONS = [
    (Fraction(7), "whole", 2),
    (Fraction(4), "whole", 0),
    (Fraction(7, 2), "half", 2),
    (Fraction(3), "half", 1),
    (Fraction(2), "half", 0),
    (Fraction(7, 4), "quarter", 2),
    (Fraction(3, 2), "quarter", 1),
    (Fraction(1), "quarter", 0),
    (Fraction(7, 8), "eighth", 2),
    (Fraction(3, 4), "eighth", 1),
    (Fraction(1, 2), "eighth", 0),
    (Fraction(7, 16), "eighth", 2),
    (Fraction(3, 8), "16th", 1),
    (Fraction(1, 4), "16th", 0),
    (Fraction(7, 32), "16th", 2),
    (Fraction(3, 16), "32nd", 1),
    (Fraction(1, 8), "32nd", 0),
    (Fraction(7, 64), "32nd", 2),
    (Fraction(3, 32), "64th", 1),
    (Fraction(1, 16), "64th", 0),
    (Fraction(7, 128), "64th", 2),
]

DURATION_QUARTERS = {
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
}

QUARTER_TICKS = 960
WHOLE_NOTE_TICKS = QUARTER_TICKS * 4

TUPLET_DURATIONS = {
    320: [(3, 2, "eighth")],
    160: [(6, 4, "16th"), (3, 2, "16th")],
    80: [(6, 4, "32nd"), (3, 2, "32nd")],
    40: [(6, 4, "64th"), (3, 2, "64th")],
}


def eid(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()[:16]
    raw = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"{raw[:11]}_{raw[11:]}"


def add_eid(parent: ET.Element, key: str) -> None:
    ET.SubElement(parent, "eid").text = eid(key)


def tokenize(ticks: int) -> list[tuple[Fraction, str, int]]:
    """Express a positive duration as normal note values in quarter units."""
    remaining = Fraction(ticks, 960)
    tokens: list[tuple[Fraction, str, int]] = []
    while remaining:
        for value, duration_type, dots in DURATIONS:
            if value <= remaining:
                tokens.append((value, duration_type, dots))
                remaining -= value
                break
        else:
            raise ValueError(
                f"Duration {ticks} ticks ({remaining} quarter notes left) "
                "requires an explicit tuplet"
            )
    return tokens


def voice_event_details(measure: dict) -> dict[int, dict[int, dict]]:
    result: dict[int, dict[int, dict]] = {
        0: {},
        1: {},
    }
    number = int(measure["number"])
    measure_ticks = int(measure["length"]) * QUARTER_TICKS
    parts = [
        part
        for event in measure["events"]
        for part in (event.get("parts") or [])
    ]
    pitches_in_measure = {
        int(pitch)
        for event in measure["events"]
        for pitch in event["pitches"]
    }
    is_double_voice = any(
        pitch in UPPER_DRUMS for pitch in pitches_in_measure
    ) and any(pitch in LOWER_DRUMS for pitch in pitches_in_measure)
    single_direction = (
        "down"
        if not any(pitch in UPPER_DRUMS for pitch in pitches_in_measure)
        else "up"
    )

    def target_voice(direction: str) -> int:
        return 0 if direction == "up" or not is_double_voice else 1

    for event in measure["events"]:
        onset = round(Fraction(str(event["time"])) * WHOLE_NOTE_TICKS)
        if onset < 0 or onset >= measure_ticks:
            raise ValueError(
                f"Measure {measure['number']}: onset {event['time']} is outside "
                f"the {measure['length']}/4 bar"
            )
        parts = event.get("parts")
        if parts:
            for part in parts:
                direction = str(part.get("voice") or "up")
                if not is_double_voice:
                    direction = single_direction
                voice = target_voice(direction)
                detail = result[voice].setdefault(
                    onset,
                    {
                        "pitches": [],
                        "duration": None,
                        "dots": 0,
                        "stem_direction": direction,
                        "graces": [],
                    },
                )
                detail["pitches"].extend(int(pitch) for pitch in part["pitches"])
                if part.get("beam_group"):
                    detail["beam_group"] = str(part["beam_group"])
                duration_type = part.get("duration")
                dots = int(part.get("dots") or 0)
                if duration_type in DURATION_QUARTERS:
                    duration = DURATION_QUARTERS[duration_type]
                    duration *= sum(
                        Fraction(1, 2**index) for index in range(dots + 1)
                    )
                    previous = detail.get("duration")
                    if previous is None or duration < previous:
                        # A template-detected cymbal may temporarily inherit a
                        # quarter-note fallback while the same voice has an
                        # explicitly beamed value.  The shortest confirmed value
                        # is the one supported by the drawn beam/flag.
                        detail["duration"] = duration
                        detail["dots"] = dots
                        detail["beam_group"] = (
                            str(part["beam_group"])
                            if part.get("beam_group")
                            else None
                        )
        else:
            event_has_upper = any(
                int(pitch) in UPPER_DRUMS for pitch in event["pitches"]
            )
            for pitch in event["pitches"]:
                fallback_voice = voice_for_pitch(int(pitch))
                if event_has_upper and int(pitch) not in {36, 44}:
                    direction = "up"
                elif event_has_upper and int(pitch) in {36, 44}:
                    direction = "down"
                else:
                    direction = "up" if fallback_voice == 0 else "down"
                if not is_double_voice:
                    direction = single_direction
                voice = target_voice(direction)
                detail = result[voice].setdefault(
                    onset,
                    {
                        "pitches": [],
                        "duration": None,
                        "dots": 0,
                        "stem_direction": direction,
                        "graces": [],
                    },
                )
                detail["pitches"].append(int(pitch))
    for event in measure["events"]:
        onset = round(Fraction(str(event["time"])) * WHOLE_NOTE_TICKS)
        for grace in event.get("graces", []):
            direction = str(grace.get("voice") or "up")
            voice = target_voice(direction)
            detail = result[voice].get(onset)
            if detail is not None:
                detail["graces"].append(
                    {
                        "pitches": [
                            int(grace_pitch)
                            for grace_pitch in grace["pitches"]
                        ],
                        "kind": str(grace.get("kind") or "acciaccatura"),
                    }
                )
    for events in result.values():
        for detail in events.values():
            detail["pitches"] = sorted(set(detail["pitches"]))

    # When an event has no beam information from OMR (or was edited manually),
    # group adjacent sub-quarter notes by beat instead of disabling beaming.
    for voice, events in result.items():
        ordered = sorted(events)
        beamable_onsets: set[int] = set()
        for previous, current in zip(ordered, ordered[1:]):
            if current - previous <= 480:
                beamable_onsets.add(previous)
                beamable_onsets.add(current)
        run: list[int] = []
        run_beat: int | None = None
        for onset in ordered:
            detail = events[onset]
            beamable = (
                not detail.get("beam_group")
                and onset in beamable_onsets
            )
            beat = onset // QUARTER_TICKS
            if not beamable or (run and beat != run_beat):
                if len(run) >= 2:
                    group = f"auto:{number}:{voice}:{run_beat}"
                    for member in run:
                        events[member]["beam_group"] = group
                run = []
            if beamable:
                if not run:
                    run_beat = beat
                run.append(onset)
        if len(run) >= 2:
            group = f"auto:{number}:{voice}:{run_beat}"
            for member in run:
                events[member]["beam_group"] = group
    return result


def voice_events(measure: dict) -> dict[int, dict[int, list[int]]]:
    details = voice_event_details(measure)
    return {
        voice: {
            onset: detail["pitches"]
            for onset, detail in events.items()
        }
        for voice, events in details.items()
    }


def add_note(parent: ET.Element, pitch: int, key: str) -> None:
    _, head, _, _, _, tpc = DRUMS[pitch]
    note = ET.SubElement(parent, "Note")
    add_eid(note, f"{key}:note:{pitch}")
    ET.SubElement(note, "pitch").text = str(pitch)
    ET.SubElement(note, "tpc").text = str(tpc)
    if head != "normal":
        ET.SubElement(note, "head").text = head


def add_chord(
    voice: ET.Element,
    duration_type: str,
    dots: int,
    pitches: list[int],
    stem_direction: str,
    key: str,
    articulations: list[str] | None = None,
    beam_mode: str | None = None,
    grace_kind: str | None = None,
) -> None:
    chord = ET.SubElement(voice, "Chord")
    add_eid(chord, f"{key}:chord")
    if beam_mode:
        ET.SubElement(chord, "BeamMode").text = beam_mode
    if dots:
        ET.SubElement(chord, "dots").text = str(dots)
    # DB Score reads MSCX children in schema order. `dots` precedes
    # `durationType`; reversing them silently drops the augmentation dot.
    ET.SubElement(chord, "durationType").text = duration_type
    if grace_kind:
        ET.SubElement(chord, grace_kind)
    for articulation_kind in articulations or []:
        articulation = ET.SubElement(chord, "Articulation")
        ET.SubElement(articulation, "subtype").text = ARTICULATION_SUBTYPES.get(
            articulation_kind,
            articulation_kind,
        )
        add_eid(articulation, f"{key}:articulation:{articulation_kind}")
    if not grace_kind:
        ET.SubElement(chord, "StemDirection").text = stem_direction
    for pitch in pitches:
        add_note(chord, pitch, key)


def add_beam(voice: ET.Element, direction: str, key: str) -> None:
    beam = ET.SubElement(voice, "Beam")
    add_eid(beam, f"{key}:beam")
    ET.SubElement(beam, "StemDirection").text = direction


def add_rest(
    voice: ET.Element,
    duration_type: str,
    dots: int,
    key: str,
) -> None:
    rest = ET.SubElement(voice, "Rest")
    add_eid(rest, f"{key}:rest")
    if dots:
        ET.SubElement(rest, "dots").text = str(dots)
    # Keep the DB Score/MuseScore MSCX schema order. Otherwise a dotted rest is
    # read as the undotted base value and every following note shifts left.
    ET.SubElement(rest, "durationType").text = duration_type


def add_tuplet(
    voice: ET.Element,
    actual: int,
    normal: int,
    base_note: str,
    key: str,
) -> None:
    tuplet = ET.SubElement(voice, "Tuplet")
    add_eid(tuplet, f"{key}:tuplet")
    ET.SubElement(tuplet, "normalNotes").text = str(normal)
    ET.SubElement(tuplet, "actualNotes").text = str(actual)
    ET.SubElement(tuplet, "baseNote").text = base_note
    number = ET.SubElement(tuplet, "Number")
    ET.SubElement(number, "style").text = "tuplet"
    ET.SubElement(number, "text").text = str(actual)


def emit_tokens(
    voice: ET.Element,
    ticks: int,
    pitches: list[int] | None,
    stem_direction: str,
    key: str,
    articulations: list[str] | None = None,
    beam_mode: str | None = None,
) -> None:
    for index, (_, duration_type, dots) in enumerate(tokenize(ticks)):
        if index == 0 and pitches:
            add_chord(
                voice,
                duration_type,
                dots,
                pitches,
                stem_direction,
                f"{key}:0",
                articulations,
                beam_mode,
            )
        else:
            add_rest(voice, duration_type, dots, f"{key}:{index}")


def emit_irregular_duration(
    voice: ET.Element,
    ticks: int,
    pitches: list[int],
    stem_direction: str,
    key: str,
    articulations: list[str] | None,
    beam_mode: str | None,
) -> None:
    """Emit an exact odd duration without moving the attack.

    This is only used when a duration cannot be represented by ordinary note
    values or by a complete triplet group.  The visible attack stays at its
    original tick; the trailing remainder is represented by rests.
    """
    def decompose(
        remaining: int,
        depth: int = 0,
    ) -> list[tuple[Fraction, str, int]] | None:
        if remaining == 0 or remaining in TUPLET_DURATIONS:
            return []
        if depth >= 8:
            return None
        for value, duration_type, dots in DURATIONS:
            value_ticks = round(value * QUARTER_TICKS)
            if value_ticks > remaining:
                continue
            tail = decompose(remaining - value_ticks, depth + 1)
            if tail is not None:
                return [(value, duration_type, dots), *tail]
        return None

    parts = decompose(ticks)
    if parts is None:
        raise ValueError(f"{key}: unsupported irregular duration {ticks} ticks")
    emitted_ticks = 0
    for part_index, (value, duration_type, dots) in enumerate(parts):
        if part_index == 0 and pitches:
            add_chord(
                voice,
                duration_type,
                dots,
                pitches,
                stem_direction,
                f"{key}:0",
                articulations,
                beam_mode,
            )
        else:
            add_rest(voice, duration_type, dots, f"{key}:{part_index}")
        emitted_ticks += round(value * QUARTER_TICKS)
    remaining = ticks - emitted_ticks
    if remaining:
        actual, normal, base_note = TUPLET_DURATIONS[remaining][0]
        add_tuplet(voice, actual, normal, base_note, f"{key}:tail")
        add_rest(voice, base_note, 0, f"{key}:tail:rest")
        ET.SubElement(voice, "endTuplet")


def duration_token_for_ticks(
    ticks: int,
) -> tuple[str, int] | None:
    for value, duration_type, dots in DURATIONS:
        if round(value * QUARTER_TICKS) == ticks:
            return duration_type, dots
    return None


Operation = tuple[
    str,
    int,
    Optional[list[int]],
    str,
    list[str],
    Optional[str],
    str,
]


def voice_operations(measure_data: dict, voice_index: int) -> list[Operation]:
    number = int(measure_data["number"])
    measure_ticks = int(measure_data["length"]) * QUARTER_TICKS
    all_details = voice_event_details(measure_data)
    events = dict(sorted(all_details[voice_index].items()))
    is_double_voice = bool(all_details[1])
    articulations_by_onset: dict[int, list[str]] = {}
    for event in measure_data["events"]:
        onset = round(Fraction(str(event["time"])) * WHOLE_NOTE_TICKS)
        if event.get("articulations"):
            articulations_by_onset.setdefault(onset, []).extend(
                str(kind) for kind in event["articulations"]
            )
    onsets = list(events)
    tuplet_note_ticks: dict[int, int] = {}
    index = 0
    while index < len(onsets):
        onset = onsets[index]
        matched = False
        for unit, variants in TUPLET_DURATIONS.items():
            for actual, _, _ in variants:
                end = index + actual
                if end > len(onsets):
                    continue
                span = onsets[index:end]
                if all(
                    current - previous == unit
                    for previous, current in zip(span, span[1:])
                ):
                    for member in span:
                        tuplet_note_ticks[member] = unit
                    index = end
                    matched = True
                    break
            if matched:
                break
        if not matched:
            index += 1
    explicit_rests: dict[int, tuple[int, str, int, bool]] = {}
    for rest in measure_data.get("rests", []):
        if rest.get("review") or rest.get("render_voice") is not None:
            # Unresolved collisions stay visible in the review project.
            # Conflicting-but-renderable rests are emitted in an overlay voice.
            continue
        direction = str(rest.get("voice") or "up")
        target_voice = 0 if direction == "up" or not is_double_voice else 1
        if target_voice != voice_index:
            continue
        duration_type = rest.get("duration")
        if duration_type not in DURATION_QUARTERS:
            continue
        dots = int(rest.get("dots") or 0)
        duration = DURATION_QUARTERS[duration_type]
        duration *= sum(Fraction(1, 2**index) for index in range(dots + 1))
        ticks = round(duration * QUARTER_TICKS)
        if ticks <= 0:
            continue
        onset = round(Fraction(str(rest["time"])) * WHOLE_NOTE_TICKS)
        if 0 <= onset < measure_ticks:
            explicit_rests.setdefault(
                onset,
                (ticks, duration_type, dots, bool(rest.get("hidden"))),
            )

    item_onsets = sorted(set(events) | set(explicit_rests))
    operations: list[Operation] = []
    cursor = 0
    for index, onset in enumerate(item_onsets):
        if onset < cursor:
            # A rest may visually overlap a sustained chord.  The identified
            # attack remains authoritative; the overlapping rest is omitted.
            if onset not in events:
                continue
            raise ValueError(
                f"Measure {number}, voice {voice_index + 1}: overlapping "
                f"event at tick {onset}"
            )
        if onset > cursor:
            operations.append(
                (
                    "rest",
                    onset - cursor,
                    None,
                    f"measure:{number}:rest:{cursor}:v{voice_index}",
                    [],
                    None,
                    "up",
                )
            )
        next_item_onset = (
            item_onsets[index + 1]
            if index + 1 < len(item_onsets)
            else measure_ticks
        )
        if onset not in events and onset in explicit_rests:
            rest_ticks, duration_type, dots, hidden = explicit_rests[onset]
            full_rest_ticks = rest_ticks
            rest_ticks = min(
                rest_ticks,
                measure_ticks - onset,
                next_item_onset - onset,
            )
            if hidden:
                operation_kind = "hidden-rest"
            elif rest_ticks == full_rest_ticks:
                operation_kind = f"explicit-rest:{duration_type}:{dots}"
            else:
                operation_kind = "rest"
            operations.append(
                (
                    operation_kind,
                    rest_ticks,
                    None,
                    f"measure:{number}:explicit-rest:{onset}:v{voice_index}",
                    [],
                    None,
                    "up",
                )
            )
            cursor = onset + rest_ticks
            continue

        detail = events[onset]
        pitches = detail["pitches"]
        next_onset = next_item_onset
        gap_ticks = next_onset - onset
        note_ticks = tuplet_note_ticks.get(onset)
        if note_ticks is not None and note_ticks > gap_ticks:
            note_ticks = None
        if note_ticks is None:
            explicit_duration = detail.get("duration")
            explicit_ticks = (
                round(explicit_duration * 960)
                if explicit_duration is not None
                else None
            )
            if explicit_ticks is None:
                note_ticks = gap_ticks
            elif explicit_ticks > gap_ticks:
                # OMR sometimes omits a rest marker.  The following onset still
                # wins so two positively identified attacks cannot be merged.
                note_ticks = gap_ticks
            else:
                note_ticks = explicit_ticks
        available_ticks = measure_ticks - onset
        if available_ticks <= 0:
            # Event starts outside/at the barline; nothing valid can be
            # emitted for this voice.
            continue
        if note_ticks > available_ticks:
            # OMR occasionally reports a note a hair longer than the bar
            # (e.g. one 32nd over). Clamp it so MuseScore can load the score
            # instead of rejecting the whole file with "Voice too long".
            note_ticks = available_ticks
        note_key = f"measure:{number}:note:{onset}:v{voice_index}"
        for grace_index, grace in enumerate(detail.get("graces", [])):
            operations.append(
                (
                    f"grace:{grace['kind']}",
                    0,
                    list(grace["pitches"]),
                    f"{note_key}:grace:{grace_index}",
                    [],
                    None,
                    str(detail.get("stem_direction") or (
                        "up" if voice_index == 0 else "down"
                    )),
                )
            )
        operations.append(
            (
                "note",
                note_ticks,
                pitches,
                note_key,
                sorted(
                    {
                        kind
                        for kind in articulations_by_onset.get(onset, [])
                        if kind not in UNWANTED_DRUM_ARTICULATIONS
                    }
                ),
                detail.get("beam_group"),
                str(detail.get("stem_direction") or (
                    "up" if voice_index == 0 else "down"
                )),
            )
        )
        cursor = onset + note_ticks
    if cursor < measure_ticks:
        operations.append(
            (
                (
                    "hidden-rest"
                    if voice_index == 1 and all_details[0]
                    else "rest"
                ),
                measure_ticks - cursor,
                None,
                f"measure:{number}:rest:{cursor}:v{voice_index}",
                [],
                None,
                "up",
            )
        )
    return operations


def element_duration_ticks(element: ET.Element) -> int:
    if element.tag not in ("Chord", "Rest"):
        return 0
    duration_type = element.findtext("durationType")
    if duration_type not in DURATION_QUARTERS:
        return 0
    duration = DURATION_QUARTERS[duration_type]
    dots = int(element.findtext("dots") or 0)
    duration *= sum(Fraction(1, 2**power) for power in range(dots + 1))
    return round(duration * QUARTER_TICKS)


def trim_overfull_measure(measure: ET.Element, measure_ticks: int) -> None:
    """Drop trailing rests/chords from voices that exceed the bar length.

    MuseScore refuses to load an mscx containing "Voice too long". OMR
    rounding occasionally produces an extra tail rest; removing trailing
    silence keeps the score loadable without altering identified attacks.
    """
    for voice in measure.findall("voice"):
        total = sum(element_duration_ticks(child) for child in voice)
        while total > measure_ticks and len(voice):
            last = voice[-1]
            if last.tag in ("Chord", "Rest"):
                total -= element_duration_ticks(last)
            voice.remove(last)


def overlay_rest_operations(
    rests: list[dict],
    measure_ticks: int,
    voice_index: int,
) -> list[Operation]:
    """Fill one overlay voice with exactly the requested visible rests."""
    operations: list[Operation] = []
    cursor = 0
    ordered = sorted(rests, key=lambda item: Fraction(str(item["time"])))
    for index, rest in enumerate(ordered):
        onset = round(Fraction(str(rest["time"])) * WHOLE_NOTE_TICKS)
        duration_type = str(rest.get("duration"))
        dots = int(rest.get("dots") or 0)
        if duration_type not in DURATION_QUARTERS or onset < cursor:
            raise ValueError(
                f"Unsupported or overlapping overlay rest at tick {onset}"
            )
        if onset > cursor:
            operations.append(
                (
                    "hidden-rest",
                    onset - cursor,
                    None,
                    f"overlay:{voice_index}:{index}:gap",
                    [],
                    None,
                    "up",
                )
            )
        duration = DURATION_QUARTERS[duration_type]
        duration *= sum(Fraction(1, 2**power) for power in range(dots + 1))
        ticks = round(duration * QUARTER_TICKS)
        if ticks <= 0 or onset + ticks > measure_ticks:
            raise ValueError(f"Overlay rest outside the measure at tick {onset}")
        operations.append(
            (
                f"explicit-rest:{duration_type}:{dots}",
                ticks,
                None,
                f"overlay:{voice_index}:{index}",
                [],
                None,
                "up",
            )
        )
        cursor = onset + ticks
    if cursor < measure_ticks:
        operations.append(
            (
                "hidden-rest",
                measure_ticks - cursor,
                None,
                f"overlay:{voice_index}:tail",
                [],
                None,
                "up",
            )
        )
    return operations


def emit_voice_operations(
    voice: ET.Element,
    operations: list[Operation],
) -> None:
    index = 0
    while index < len(operations):
        (
            kind,
            ticks,
            pitches,
            key,
            articulations,
            beam_group,
            stem_direction,
        ) = operations[index]
        if kind.startswith("explicit-rest:"):
            _, duration_type, dots_text = kind.split(":", 2)
            add_rest(voice, duration_type, int(dots_text), key)
            index += 1
            continue
        if kind.startswith("grace:"):
            grace_kind = kind.split(":", 1)[1]
            add_chord(
                voice,
                "eighth",
                0,
                pitches or [],
                stem_direction,
                key,
                grace_kind=grace_kind,
            )
            index += 1
            continue
        try:
            tokenize(ticks)
        except ValueError:
            candidates = TUPLET_DURATIONS.get(ticks)
            if candidates is None:
                emit_irregular_duration(
                    voice,
                    ticks,
                    pitches or [],
                    stem_direction,
                    key,
                    articulations,
                    beam_mode=None,
                )
                index += 1
                continue
            selected_group: tuple[
                int,
                int,
                str,
                list[Operation],
            ] | None = None
            for actual, normal, base_note in candidates:
                base_ticks = round(DURATION_QUARTERS[base_note] * QUARTER_TICKS)
                expected_ticks = normal * base_ticks
                total_ticks = 0
                members: list[Operation] = []
                for operation in operations[index:]:
                    if operation[0].startswith("explicit-rest:"):
                        break
                    try:
                        tokenize(operation[1])
                    except ValueError:
                        pass
                    else:
                        break
                    total_ticks += operation[1]
                    members.append(operation)
                    if total_ticks >= expected_ticks:
                        break
                if total_ticks == expected_ticks:
                    selected_group = (
                        actual,
                        normal,
                        base_note,
                        members,
                    )
                    break
            if selected_group is None:
                emit_irregular_duration(
                    voice,
                    ticks,
                    pitches or [],
                    stem_direction,
                    key,
                    articulations,
                    beam_mode=None,
                )
                index += 1
                continue
            actual, normal, base_note, members = selected_group
            add_tuplet(voice, actual, normal, base_note, key)
            for operation in members:
                (
                    op_kind,
                    op_ticks,
                    op_pitches,
                    op_key,
                    op_articulations,
                    _,
                    op_stem_direction,
                ) = operation
                inner_ticks = round(
                    Fraction(op_ticks) * actual / normal
                )
                token = duration_token_for_ticks(inner_ticks)
                if token is None:
                    raise ValueError(
                        f"{op_key}: {op_ticks} ticks do not fit "
                        f"the {actual}:{normal} tuplet"
                    )
                duration_type, dots = token
                if op_kind == "note":
                    add_chord(
                        voice,
                        duration_type,
                        dots,
                        op_pitches or [],
                        op_stem_direction,
                        op_key,
                        op_articulations,
                    )
                else:
                    add_rest(voice, duration_type, dots, op_key)
            ET.SubElement(voice, "endTuplet")
            index += len(members)
            continue

        previous_beam_group = next(
            (
                operation[5]
                for operation in reversed(operations[:index])
                if not operation[0].startswith("grace:")
            ),
            None,
        )
        next_beam_group = (
            next(
                (
                    operation[5]
                    for operation in operations[index + 1:]
                    if not operation[0].startswith("grace:")
                ),
                None,
            )
        )
        beam_mode = None
        if kind == "note" and beam_group:
            if beam_group != previous_beam_group:
                add_beam(
                    voice,
                    stem_direction,
                    key,
                )
                beam_mode = "begin"
            elif beam_group == next_beam_group:
                beam_mode = "mid"
            else:
                beam_mode = "end"
        elif kind == "note" and ticks <= 480:
            beam_mode = "no"

        if kind == "note":
            emit_tokens(
                voice,
                ticks,
                pitches,
                stem_direction,
                key,
                articulations,
                beam_mode,
            )
        else:
            previous_rest_count = len(voice.findall("Rest"))
            emit_tokens(voice, ticks, None, "up", key)
            if kind == "hidden-rest":
                for rest in voice.findall("Rest")[previous_rest_count:]:
                    ET.SubElement(rest, "visible").text = "0"
        index += 1


def add_measure(
    staff: ET.Element,
    measure_data: dict,
    *,
    first: bool,
    previous_beats: int | None,
    tempo: int,
    break_after: str | None,
) -> ET.Element:
    number = int(measure_data["number"])
    beats = int(measure_data["length"])
    measure_ticks = beats * QUARTER_TICKS
    measure = ET.SubElement(staff, "Measure")
    add_eid(measure, f"measure:{number}")
    if measure_data.get("start_repeat"):
        ET.SubElement(measure, "startRepeat")
    if measure_data.get("end_repeat"):
        ET.SubElement(measure, "endRepeat").text = str(
            max(2, int(measure_data.get("repeat_count", 2)))
        )
    if break_after:
        layout_break = ET.SubElement(measure, "LayoutBreak")
        add_eid(layout_break, f"system-break:{number}")
        ET.SubElement(layout_break, "subtype").text = break_after

    events_by_voice = voice_events(measure_data)
    voice_indices = [0]
    has_lower_rests = any(
        str(rest.get("voice") or "up") == "down"
        for rest in measure_data.get("rests", [])
    )
    if events_by_voice[1] or has_lower_rests:
        voice_indices.append(1)
    overlay_by_voice = {
        2: [
            rest
            for rest in measure_data.get("rests", [])
            if int(rest.get("render_voice", -1)) == 2
        ],
        3: [
            rest
            for rest in measure_data.get("rests", [])
            if int(rest.get("render_voice", -1)) == 3
        ],
    }
    if any(overlay_by_voice.values()):
        voice_indices = [0, 1, 2, 3]
    for voice_index in voice_indices:
        voice = ET.SubElement(measure, "voice")

        if first and voice_index == 0:
            clef = ET.SubElement(voice, "Clef")
            ET.SubElement(clef, "concertClefType").text = "PERC"
            ET.SubElement(clef, "transposingClefType").text = "PERC"
            ET.SubElement(clef, "isHeader").text = "1"
            add_eid(clef, "clef:1")
        if previous_beats != beats and (voice_index == 0 or first):
            time_signature = ET.SubElement(voice, "TimeSig")
            add_eid(time_signature, f"time:{number}")
            ET.SubElement(time_signature, "sigN").text = str(beats)
            ET.SubElement(time_signature, "sigD").text = "4"
        if first and voice_index == 0:
            tempo_element = ET.SubElement(voice, "Tempo")
            add_eid(tempo_element, "tempo:1")
            ET.SubElement(tempo_element, "tempo").text = str(tempo / 60)
            ET.SubElement(tempo_element, "followText").text = "1"
            text = ET.SubElement(tempo_element, "text")
            symbol = ET.SubElement(text, "sym")
            symbol.text = "metNoteQuarterUp"
            symbol.tail = f" = {tempo}"

        if voice_index >= 2:
            operations = overlay_rest_operations(
                overlay_by_voice[voice_index],
                measure_ticks,
                voice_index,
            )
        else:
            operations = voice_operations(measure_data, voice_index)
        if not operations:
            rest_key = f"measure:{number}:voice:{voice_index}"
            add_rest(voice, "measure", 0, rest_key)
            if (voice_index == 0 and events_by_voice[1]) or voice_index >= 2:
                rest = voice.findall("Rest")[-1]
                ET.SubElement(rest, "visible").text = "0"
            continue
        emit_voice_operations(voice, operations)

    return measure


def attach_curves(
    score: ET.Element,
    staff: ET.Element,
    payload: dict,
) -> None:
    """Attach ties and phrase slurs in DB Score 5.0.7 native format.

    Ties are stored on their ending note with start/end EID references.
    Phrase slurs are score-level spanners.  Older inline ``Spanner`` elements
    are silently discarded when DB Score saves the score.
    """
    notes_by_onset: dict[tuple[int, int, int, int], ET.Element] = {}
    chord_by_note: dict[ET.Element, ET.Element] = {}
    for measure, measure_data in zip(
        staff.findall("Measure"),
        payload["measures"],
    ):
        number = int(measure_data["number"])
        for voice_index, voice in enumerate(measure.findall("voice")):
            cursor = Fraction(0)
            ratio = Fraction(1)
            tuplet_stack: list[Fraction] = []
            for element in list(voice):
                if element.tag == "Tuplet":
                    tuplet_stack.append(ratio)
                    ratio *= Fraction(
                        int(element.findtext("normalNotes")),
                        int(element.findtext("actualNotes")),
                    )
                    continue
                if element.tag == "endTuplet":
                    ratio = tuplet_stack.pop() if tuplet_stack else Fraction(1)
                    continue
                if element.tag not in {"Chord", "Rest"}:
                    continue
                is_grace = (
                    element.tag == "Chord"
                    and (
                        element.find("acciaccatura") is not None
                        or element.find("appoggiatura") is not None
                    )
                )
                if element.tag == "Chord" and not is_grace:
                    onset_ticks = round(cursor * QUARTER_TICKS)
                    for note in element.findall("Note"):
                        pitch_text = note.findtext("pitch")
                        if pitch_text is not None:
                            notes_by_onset[
                                (number, onset_ticks, voice_index, int(pitch_text))
                            ] = note
                            chord_by_note[note] = element
                duration_type = element.findtext("durationType") or "quarter"
                duration = (
                    Fraction(int(measure_data["length"]))
                    if duration_type == "measure"
                    else DURATION_QUARTERS[duration_type]
                )
                dots = int(element.findtext("dots") or 0)
                duration *= sum(
                    Fraction(1, 2**index)
                    for index in range(dots + 1)
                )
                if not is_grace:
                    cursor += duration * ratio
    measure_offsets: dict[int, Fraction] = {}
    offset = Fraction(0)
    measure_lookup = {}
    for measure, measure_data in zip(
        staff.findall("Measure"),
        payload["measures"],
    ):
        number = int(measure_data["number"])
        measure_offsets[number] = offset
        measure_lookup[number] = measure_data
        offset += int(measure_data["length"])

    tie_ends: dict[tuple[str, int, str], list[tuple[Fraction, int, int]]] = {}
    slur_ends: dict[str, list[tuple[Fraction, int]]] = {}
    for measure_data in payload["measures"]:
        number = int(measure_data["number"])
        details = voice_event_details(measure_data)
        for event in measure_data.get("events", []):
            onset = Fraction(str(event["time"]))
            onset_ticks = round(onset * WHOLE_NOTE_TICKS)
            absolute_tick = measure_offsets[number] + onset * 4
            for tie in event.get("ties", []):
                role = str(tie.get("role") or "")
                pitch = int(tie.get("pitch") or 0)
                tie_id = str(tie.get("id") or "")
                if role == "start":
                    continue
                tie_ends.setdefault((tie_id, pitch, role), []).append(
                    (absolute_tick, number, onset_ticks)
                )
            for slur in event.get("slurs", []):
                if str(slur.get("role") or "") == "end":
                    slur_ends.setdefault(str(slur.get("id") or ""), []).append(
                        (absolute_tick, number)
                    )

    def note_for(
        measure_number: int,
        onset_ticks: int,
        pitch: int,
    ) -> tuple[ET.Element, ET.Element, int]:
        measure_data = measure_lookup[measure_number]
        onset = Fraction(onset_ticks, WHOLE_NOTE_TICKS)
        details = voice_event_details(measure_data)
        voice_index = next(
            (
                index
                for index, voice_details in details.items()
                if pitch in voice_details.get(onset_ticks, {}).get("pitches", [])
            ),
            None,
        )
        if voice_index is None:
            raise ValueError(
                f"Measure {measure_number}: cannot locate tied pitch {pitch} "
                f"at {onset}"
            )
        note = notes_by_onset.get(
            (measure_number, onset_ticks, voice_index, pitch)
        )
        if note is None:
            raise ValueError(
                f"Measure {measure_number}: missing tied note "
                f"pitch {pitch} at {onset}"
            )
        return note, chord_by_note[note], voice_index

    ties_seen = set()
    for measure_data in payload["measures"]:
        number = int(measure_data["number"])
        for event in measure_data.get("events", []):
            onset_ticks = round(Fraction(str(event["time"])) * WHOLE_NOTE_TICKS)
            start_tick = measure_offsets[number] + Fraction(
                str(event["time"])
            ) * 4
            for tie in event.get("ties", []):
                if str(tie.get("role") or "") != "start":
                    continue
                pitch = int(tie.get("pitch") or 0)
                tie_id = str(tie.get("id") or "")
                key = (tie_id, pitch)
                if key in ties_seen:
                    continue
                ties_seen.add(key)
                ends = tie_ends.get((tie_id, pitch, "end"), [])
                if len(ends) != 1:
                    raise ValueError(
                        f"Tie {tie_id} pitch {pitch} has {len(ends)} endings"
                    )
                end_tick, end_measure, end_onset = ends[0]
                if end_tick <= start_tick:
                    raise ValueError(
                        f"Tie {tie_id} ends before it starts"
                    )
                start_note, _, _ = note_for(
                    number,
                    onset_ticks,
                    pitch,
                )
                end_note, _, voice_index = note_for(
                    end_measure,
                    end_onset,
                    pitch,
                )
                tie = ET.Element("Tie")
                ET.SubElement(tie, "startElement").text = (
                    start_note.findtext("eid") or ""
                )
                ET.SubElement(tie, "endElement").text = (
                    end_note.findtext("eid") or ""
                )
                add_eid(tie, f"tie:{tie_id}:{pitch}")
                ET.SubElement(tie, "track").text = str(
                    voice_index
                )
                end_note.insert(
                    list(end_note).index(end_note.find("eid")) + 1,
                    tie,
                )

    slurs_seen = set()
    spanner_map = score.find("SpannerMap")
    if spanner_map is None:
        spanner_map = ET.SubElement(score, "SpannerMap")
    for measure_data in payload["measures"]:
        number = int(measure_data["number"])
        for event in measure_data.get("events", []):
            onset = Fraction(str(event["time"]))
            onset_ticks = round(onset * WHOLE_NOTE_TICKS)
            absolute_tick = measure_offsets[number] + onset * 4
            for slur in event.get("slurs", []):
                if str(slur.get("role") or "") != "start":
                    continue
                slur_id = str(slur.get("id") or "")
                if slur_id in slurs_seen:
                    continue
                slurs_seen.add(slur_id)
                endpoints = slur_ends.get(slur_id, [])
                if len(endpoints) != 1:
                    raise ValueError(
                        f"Slur {slur_id} has {len(endpoints)} endings"
                    )
                end_tick, end_measure = endpoints[0]
                if end_tick <= absolute_tick:
                    raise ValueError(
                        f"Slur {slur_id} ends before it starts"
                    )
                pitches = [
                    int(pitch)
                    for pitch in event.get("pitches", [])
                ]
                if not pitches:
                    raise ValueError(f"Slur {slur_id} starts without a note")
                _, start_chord, start_voice = note_for(
                    number,
                    onset_ticks,
                    pitches[0],
                )
                end_measure_data = measure_lookup[end_measure]
                end_events = [
                    candidate
                    for candidate in end_measure_data.get("events", [])
                    if (
                        measure_offsets[end_measure]
                        + Fraction(str(candidate["time"])) * 4
                        == end_tick
                    )
                ]
                if not end_events:
                    raise ValueError(f"Slur {slur_id} has no ending chord")
                end_event = end_events[0]
                end_onset_ticks = round(
                    Fraction(str(end_event["time"])) * WHOLE_NOTE_TICKS
                )
                _, end_chord, _ = note_for(
                    end_measure,
                    end_onset_ticks,
                    int(end_event["pitches"][0]),
                )
                slur = ET.SubElement(spanner_map, "Slur")
                ET.SubElement(slur, "startElement").text = (
                    start_chord.findtext("eid") or ""
                )
                ET.SubElement(slur, "endElement").text = (
                    end_chord.findtext("eid") or ""
                )
                add_eid(slur, f"slur:{slur_id}")
                ET.SubElement(slur, "track").text = str(start_voice)


def build(payload: dict, output: Path) -> None:
    root = ET.Element("museScore", version="5.00")
    ET.SubElement(root, "programVersion").text = "5.0.7"
    ET.SubElement(root, "programRevision").text = "0734901"
    score = ET.SubElement(root, "Score")
    ET.SubElement(score, "Division").text = "480"
    ET.SubElement(score, "showInvisible").text = "1"
    ET.SubElement(score, "showUnprintable").text = "1"
    ET.SubElement(score, "showFrames").text = "1"
    ET.SubElement(score, "showMargins").text = "0"
    ET.SubElement(score, "open").text = "1"
    meta = ET.SubElement(score, "metaTag", name="workTitle")
    meta.text = payload["title"]
    ET.SubElement(score, "metaTag", name="copyright").text = "版权 ©"
    ET.SubElement(score, "metaTag", name="platform").text = "image-to-db"

    part = ET.SubElement(score, "Part", id="1")
    staff = ET.SubElement(part, "Staff")
    staff_type = ET.SubElement(staff, "StaffType", group="percussion")
    ET.SubElement(staff_type, "name").text = "perc5Line"
    ET.SubElement(staff_type, "keysig").text = "0"

    instrument = ET.SubElement(part, "Instrument", id="drumset")
    ET.SubElement(instrument, "trackName").text = "Drum Kit"
    ET.SubElement(instrument, "instrumentId").text = "drum.group.set"
    ET.SubElement(instrument, "useDrumset").text = "1"
    ET.SubElement(instrument, "percussionPanelColumns").text = "8"
    for pitch, (name, head, line, voice, stem, _) in DRUMS.items():
        drum = ET.SubElement(instrument, "Drum", pitch=str(pitch))
        ET.SubElement(drum, "head").text = head
        ET.SubElement(drum, "line").text = str(line)
        ET.SubElement(drum, "voice").text = str(voice)
        ET.SubElement(drum, "name").text = name
        ET.SubElement(drum, "stem").text = str(stem)
    ET.SubElement(instrument, "clef").text = "PERC"
    ET.SubElement(instrument, "singleNoteDynamics").text = "0"
    channel = ET.SubElement(instrument, "Channel")
    ET.SubElement(channel, "controller", ctrl="0", value="1")
    ET.SubElement(channel, "controller", ctrl="10", value="63")
    ET.SubElement(channel, "program", value="0")
    ET.SubElement(channel, "synti").text = "Fluid"

    staff_score = ET.SubElement(score, "Staff", id="1")
    box = ET.SubElement(staff_score, "VBox")
    ET.SubElement(box, "height").text = "10"
    title = ET.SubElement(box, "Text")
    ET.SubElement(title, "style").text = "title"
    ET.SubElement(title, "size").text = "25.1575"
    ET.SubElement(title, "text").text = payload["title"]

    previous_beats = None
    for index, measure_data in enumerate(payload["measures"]):
        next_measure = (
            payload["measures"][index + 1]
            if index + 1 < len(payload["measures"])
            else None
        )
        break_after = None
        if next_measure is not None:
            if next_measure.get("page_start"):
                break_after = "page"
            elif next_measure.get("system_start"):
                break_after = "line"
        measure_element = add_measure(
            staff_score,
            measure_data,
            first=index == 0,
            previous_beats=previous_beats,
            tempo=int(payload["tempo"]),
            break_after=break_after,
        )
        trim_overfull_measure(
            measure_element,
            int(measure_data["length"]) * QUARTER_TICKS,
        )
        previous_beats = int(measure_data["length"])

    attach_curves(score, staff_score, payload)

    volta_spans: list[tuple[int, int, int, bool]] = []
    span_start: int | None = None
    span_end: int | None = None
    span_number: int | None = None
    span_ends_repeat = False
    for measure_data in payload["measures"]:
        number = int(measure_data["number"])
        volta = measure_data.get("volta")
        if volta != span_number:
            if (
                span_start is not None
                and span_end is not None
                and span_number is not None
            ):
                volta_spans.append(
                    (span_number, span_start, span_end, span_ends_repeat)
                )
            span_start = number if volta is not None else None
            span_end = number if volta is not None else None
            span_number = int(volta) if volta is not None else None
            span_ends_repeat = bool(measure_data.get("end_repeat"))
        else:
            span_end = number
            span_ends_repeat = bool(measure_data.get("end_repeat"))
    if span_start is not None and span_end is not None and span_number is not None:
        volta_spans.append((span_number, span_start, span_end, span_ends_repeat))

    if volta_spans:
        spanner_map = ET.SubElement(score, "SpannerMap")
        for number, start, end, has_end_hook in volta_spans:
            volta = ET.SubElement(spanner_map, "Volta")
            if has_end_hook:
                ET.SubElement(volta, "endHookType").text = "1"
            ET.SubElement(volta, "beginText").text = str(number)
            ET.SubElement(volta, "startElement").text = eid(f"measure:{start}")
            ET.SubElement(volta, "endElement").text = eid(f"measure:{end}")
            add_eid(volta, f"volta:{start}:{end}")
            ET.SubElement(volta, "track").text = "0"
            ET.SubElement(volta, "endings").text = str(number)

    ET.indent(root, space="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.events.read_text(encoding="utf-8"))
    build(payload, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
