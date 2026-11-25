#!/usr/bin/env python3
"""Extract a reviewable drum event map from Audiveris OMR data.

Audiveris noteheads and slots are evidence, not authoritative rhythm.  The
converter resolves each measure through one deterministic arbitration pipeline:
cross-voice separation, regular-pulse recovery, printed beam durations,
bar-wide grid fallback, voice/rest alignment, and sparse-sixteenth handling.
The final event map is then locked by a per-measure contract before a DB绘谱
file can be published.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

import cv2
import numpy as np
from PIL import Image, ImageDraw

from layout_policy import LOWER_DRUMS, UPPER_DRUMS


PITCH_COLORS = {
    36: (0, 120, 255),
    37: (0, 165, 255),
    38: (220, 0, 70),
    42: (0, 160, 0),
    43: (110, 80, 220),
    44: (150, 100, 230),
    45: (120, 70, 210),
    46: (0, 190, 100),
    47: (70, 120, 230),
    48: (40, 90, 220),
    49: (220, 100, 0),
    51: (0, 180, 220),
    53: (160, 0, 200),
    56: (180, 100, 0),
    57: (220, 40, 0),
}

ONSET_GROUP_X_TOLERANCE = 12.0

SHAPE_TO_DRUM = {
    (3, "NOTEHEAD_BLACK"): 36,
    (4, "NOTEHEAD_BLACK"): 36,
    (-1, "NOTEHEAD_BLACK"): 38,
    (-1, "NOTEHEAD_CROSS"): 37,
    (-5, "NOTEHEAD_CROSS"): 42,
    (-3, "NOTEHEAD_CROSS"): 46,
    (5, "NOTEHEAD_CROSS"): 44,
    (-8, "NOTEHEAD_CROSS"): 55,
    (-7, "NOTEHEAD_CROSS"): 57,
    (-6, "NOTEHEAD_CROSS"): 49,
    (-6, "NOTEHEAD_DIAMOND_FILLED"): 49,
    (-4, "NOTEHEAD_BLACK"): 50,
    (-4, "NOTEHEAD_CROSS"): 51,
    (-2, "NOTEHEAD_DIAMOND_FILLED"): 54,
    (-2, "NOTEHEAD_CROSS"): 51,
    (-3, "NOTEHEAD_TRIANGLE_DOWN_FILLED"): 56,
    (-2, "NOTEHEAD_TRIANGLE_DOWN_FILLED"): 56,
    # In the source book, a diamond-shaped cymbal head means Ride, even
    # though Audiveris labels the glyph as "filled". DB绘谱 represents that
    # notation as MIDI 51 (Ride Cymbal), not Ride Bell.
    (-4, "NOTEHEAD_DIAMOND_FILLED"): 51,
    (1, "NOTEHEAD_BLACK"): 43,
    (0, "NOTEHEAD_BLACK"): 45,
    (-2, "NOTEHEAD_BLACK"): 47,
    (-3, "NOTEHEAD_BLACK"): 48,
    (2, "NOTEHEAD_BLACK"): 41,
    (-3, "NOTEHEAD_VOID"): 48,
    (1, "NOTEHEAD_VOID"): 43,
    (2, "NOTEHEAD_VOID"): 41,
}


@dataclass
class Slot:
    x: float
    time: Fraction


@dataclass
class Measure:
    number: int
    left: float
    right: float
    slots: list[Slot] = field(default_factory=list)
    omr_duration: Fraction = Fraction(0)
    system_start: bool = False
    start_repeat: bool = False
    end_repeat: bool = False
    repeat_count: int = 2
    volta: int | None = None


@dataclass
class Head:
    source_id: str
    x: float
    y: float
    pitch_position: int
    shape: str
    drum: int | None
    stem_x: float | None = None
    stem_direction: str | None = None
    beam_count: int = 0
    flag_count: int = 0
    beam_group: str | None = None
    dots: int = 0
    measure: int | None = None
    time: Fraction | None = None
    time_verified: bool = False
    slot_error: float | None = None
    graces: list["GraceSymbol"] = field(default_factory=list)
    tie_start: str | None = None
    tie_end: str | None = None
    slur_starts: list[str] = field(default_factory=list)
    slur_ends: list[str] = field(default_factory=list)


@dataclass
class GraceSymbol:
    x: float
    y: float
    drum: int
    kind: str = "acciaccatura"


@dataclass
class RestSymbol:
    source_id: str
    x: float
    y: float
    pitch_position: float
    shape: str
    voice: str
    duration_type: str
    dots: int = 0
    measure: int | None = None
    time: Fraction | None = None
    slot_error: float | None = None
    review: bool = False


@dataclass
class Articulation:
    x: float
    y: float
    kind: str


def read_omr_xml(omr_path: Path) -> ET.Element:
    with zipfile.ZipFile(omr_path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", name)
        ]
        if len(candidates) != 1:
            raise ValueError(f"Expected one sheet XML in {omr_path}, got {candidates}")
        return ET.fromstring(archive.read(candidates[0]))


def validate_drum_sheet(root: ET.Element) -> None:
    """Reject non-percussion scores before any drum-specific interpretation."""
    clefs = [
        clef
        for clef in root.findall(".//clef")
        if clef.get("kind") is not None or clef.get("shape") is not None
    ]
    if not clefs:
        raise ValueError("未能识别谱号，无法确认这是架子鼓鼓谱")
    non_percussion = {
        clef.get("kind", "UNKNOWN")
        for clef in clefs
        if clef.get("kind") != "PERCUSSION"
    }
    if non_percussion:
        kinds = "、".join(sorted(non_percussion))
        raise ValueError(
            "当前 AI 转谱仅支持架子鼓鼓谱；检测到非打击乐谱号："
            f"{kinds}"
        )


def bounds_center(element: ET.Element) -> tuple[float, float, float, float]:
    bounds = element.find("bounds")
    if bounds is None:
        raise ValueError(f"{element.tag} has no bounds")
    x = float(bounds.get("x"))
    y = float(bounds.get("y"))
    w = float(bounds.get("w"))
    h = float(bounds.get("h"))
    return x + w / 2, y + h / 2, w, h


REST_SHAPES = {
    "WHOLE_REST": "whole",
    "HALF_REST": "half",
    "QUARTER_REST": "quarter",
    "EIGHTH_REST": "eighth",
    "ONE_16TH_REST": "16th",
    "16TH_REST": "16th",
    "ONE_32ND_REST": "32nd",
    "32ND_REST": "32nd",
    "ONE_64TH_REST": "64th",
    "64TH_REST": "64th",
}

NOTE_VALUE_FRACTIONS = {
    "whole": Fraction(1),
    "half": Fraction(1, 2),
    "quarter": Fraction(1, 4),
    "eighth": Fraction(1, 8),
    "16th": Fraction(1, 16),
    "32nd": Fraction(1, 32),
    "64th": Fraction(1, 64),
}

# Curves in the source drum notation are reserved for the cymbal pulse.
# Hi-Hat (closed/open/pedal) and Ride/Bell may sustain or be phrased with a
# curve; Bass Drum, Snare and Toms are always separate strokes in this score
# family.  Audiveris sometimes draws a tie/slur over those strokes by
# following a beam edge, so unsupported instrument pairs are discarded before
# they reach the DB绘谱 event map.
CURVE_DRUMS = {42, 44, 46, 49, 51, 53}
# Curves below this glyph grade are beam-edge artifacts rather than printed
# ties/slurs (Audiveris commonly reports ~0.28 for them).
CURVE_MIN_GRADE = 0.35


def augmentation_dot_counts(system: ET.Element) -> collections.Counter[str]:
    """Resolve printed augmentation dots to their owning head/rest.

    Audiveris represents a double dot as two linked relations:
    ``dot #2 -> dot #1`` (``double-dot``) and ``dot #1 -> note/rest``
    (``augmentation``). The old parser incremented the dot's own id instead
    of the owning note, so double-dotted values were lost.

    Rest hooks are occasionally misclassified as tall, narrow augmentation
    dots. Requiring a roughly square glyph prevents a following eighth rest
    from being attached to the preceding 16th-note kick.
    """
    elements = {
        element.get("id"): element
        for element in system.iter()
        if element.get("id")
    }

    def valid_dot(
        element_id: str,
        owner_id: str | None = None,
    ) -> bool:
        element = elements.get(element_id)
        bounds = element.find("bounds") if element is not None else None
        if bounds is None:
            return False
        try:
            width = float(bounds.get("w"))
            height = float(bounds.get("h"))
        except (TypeError, ValueError):
            return False
        if not (width > 0 and height > 0 and 0.7 <= width / height <= 1.4):
            return False
        owner = elements.get(owner_id or "")
        if owner is not None and owner.tag == "head":
            owner_bounds = owner.find("bounds")
            if owner_bounds is None:
                return False
            dot_x = float(bounds.get("x")) + width / 2
            head_x = float(owner_bounds.get("x")) + float(
                owner_bounds.get("w")
            ) / 2
            # A true dot sits close to the right edge of its notehead. The
            # round head of a following eighth rest is commonly 30+ px away
            # and must not turn the kick into a dotted value.
            return 4.0 <= dot_x - head_x <= 28.0
        return True

    counts: collections.Counter[str] = collections.Counter()
    dot_targets: dict[str, str] = {}
    double_dots: list[tuple[str, str]] = []
    for relation in system.findall(".//relation"):
        relation_type = next(iter(relation), None)
        if relation_type is None:
            continue
        source = relation.get("source", "")
        target = relation.get("target", "")
        if relation_type.tag == "augmentation":
            dot_targets[source] = target
            if valid_dot(source, target):
                counts[target] += 1
        elif relation_type.tag == "double-dot":
            double_dots.append((source, target))

    for source, target in double_dots:
        owner = dot_targets.get(target)
        if not valid_dot(source, owner):
            continue
        # Audiveris 5.11 chains the second dot to the first. Support older
        # layouts where the relation targets the note/rest directly.
        if owner is not None:
            if valid_dot(target):
                counts[owner] += 1
        elif target:
            counts[target] += 2
    return counts


def parse_rests(system: ET.Element) -> list[RestSymbol]:
    dot_counts = augmentation_dot_counts(system)
    result = []
    for element in system.findall(".//rest"):
        shape = element.get("shape", "")
        duration_type = REST_SHAPES.get(shape)
        if duration_type is None or element.find("bounds") is None:
            continue
        x, y, _, _ = bounds_center(element)
        try:
            pitch_position = float(element.get("pitch", "0"))
        except ValueError:
            pitch_position = 0.0
        # Drum rests are vertically separated by voice.  Rests on the lower
        # side belong to the bass-drum/pedal voice; upper rests belong to the
        # snare/cymbal/tom voice.
        voice = "down" if pitch_position >= 2.5 else "up"
        result.append(
            RestSymbol(
                source_id=element.get("id", ""),
                x=x,
                y=y,
                pitch_position=pitch_position,
                shape=shape,
                voice=voice,
                duration_type=duration_type,
                dots=dot_counts.get(element.get("id", ""), 0),
            )
        )
    return result


def parse_stacks(
    root: ET.Element,
    counts: list[int] | None = None,
) -> tuple[list[list[Measure]], list[ET.Element]]:
    systems = root.findall("./page/system")
    if counts is not None and len(counts) != len(systems):
        raise ValueError(f"Expected {len(systems)} system counts, got {len(counts)}")

    systems_measures: list[list[Measure]] = []
    number = 1
    for system_index, system in enumerate(systems):
        stacks = system.findall("stack")
        expected_count = counts[system_index] if counts else len(stacks)
        accepted = [stack for stack in stacks if Fraction(stack.get("duration", "0")) > 0]
        dropped_short_tail = False
        if len(accepted) > 1 and Fraction(accepted[-1].get("duration", "0")) < Fraction(1, 2):
            accepted = accepted[:-1]
            dropped_short_tail = True

        if len(accepted) == expected_count:
            selected = accepted
        elif dropped_short_tail and len(accepted) < expected_count:
            selected = accepted
        elif len(stacks) == expected_count:
            selected = stacks
        elif len(accepted) < expected_count:
            # A time-signature barline can be missed in the middle of a system.
            # The caller supplies explicit split positions to restore those bars.
            selected = accepted
        else:
            raise ValueError(
                f"System {system_index + 1}: expected {expected_count} measures, "
                f"OMR has {len(stacks)} stacks ({len(accepted)} non-empty)"
            )

        system_measures: list[Measure] = []
        for stack_index, stack in enumerate(selected):
            slots = [
                Slot(float(slot.get("x-offset")), Fraction(slot.get("time-offset")))
                for slot in stack.findall("slot")
            ]
            slots.sort(key=lambda slot: slot.x)
            system_measures.append(
                Measure(
                    number=number,
                    left=float(stack.get("left")),
                    right=float(stack.get("right")),
                    slots=slots,
                    omr_duration=Fraction(stack.get("duration", "0")),
                    system_start=stack_index == 0,
                )
            )
            number += 1
        systems_measures.append(system_measures)
    return systems_measures, systems


def split_measure(
    measures: list[Measure],
    index: int,
    split_x: float,
    second_slots: list[Slot] | None = None,
) -> None:
    """Insert a barline missed because of an inline meter change."""
    original = measures[index]
    if not original.left < split_x < original.right:
        raise ValueError(f"Split x={split_x} is outside measure {original.number}")
    left = Measure(
        number=original.number,
        left=original.left,
        right=split_x,
        slots=[s for s in original.slots if s.x <= split_x - original.left],
        omr_duration=Fraction(0),
        system_start=original.system_start,
        start_repeat=original.start_repeat,
        end_repeat=False,
        repeat_count=original.repeat_count,
        volta=original.volta,
    )
    right = Measure(
        number=original.number + 1,
        left=split_x,
        right=original.right,
        slots=second_slots or [],
        omr_duration=Fraction(0),
        system_start=False,
        start_repeat=False,
        end_repeat=original.end_repeat,
        repeat_count=original.repeat_count,
        volta=None,
    )
    for slot in original.slots:
        if slot.x > split_x - original.left:
            right.slots.append(Slot(slot.x + original.left - split_x, slot.time))
    measures[index : index + 1] = [left, right]


def parse_heads(system: ET.Element) -> list[Head]:
    heads: list[Head] = []
    for element in system.findall(".//head"):
        if element.find("bounds") is None:
            continue
        x, y, _, _ = bounds_center(element)
        pitch_position = int(element.get("pitch"))
        shape = element.get("shape", "")
        # Small noteheads are grace notes. They do not occupy a rhythmic slot
        # and must never become ordinary attacks. They are collected by the
        # dedicated grace-note recognizer below.
        if shape.endswith("_SMALL"):
            continue
        drum = (
            53
            if shape == "NOTEHEAD_DIAMOND_FILLED"
            else SHAPE_TO_DRUM.get((pitch_position, shape))
        )
        heads.append(
            Head(
                source_id=element.get("id", ""),
                x=x,
                y=y,
                pitch_position=pitch_position,
                shape=shape,
                drum=drum,
            )
        )
    return heads


def annotate_head_rhythm(system: ET.Element, heads: list[Head]) -> None:
    """Add source stem direction, beam/flag count, and dots to noteheads."""
    by_id = {head.source_id: head for head in heads}
    elements = {
        element.get("id"): element
        for element in system.iter()
        if element.get("id")
    }
    head_stems: dict[str, str] = {}
    head_sides: dict[str, str] = {}
    stem_beams: dict[str, set[str]] = collections.defaultdict(set)
    stem_flags: collections.Counter[str] = collections.Counter()
    beam_groups: dict[str, str] = {}
    chord_stems: dict[str, str] = {}
    chord_onsets: dict[str, Fraction] = {}
    stems = []
    for stem in system.findall(".//stem"):
        bounds = stem.find("bounds")
        if bounds is None:
            continue
        stem_x = float(bounds.get("x")) + float(bounds.get("w")) / 2
        stem_top = float(bounds.get("y"))
        stem_bottom = stem_top + float(bounds.get("h"))
        stems.append((stem.get("id", ""), stem_x, stem_top, stem_bottom))

    for relation in system.findall(".//relation"):
        relation_type = next(iter(relation), None)
        if relation_type is None:
            continue
        source = relation.get("source", "")
        target = relation.get("target", "")
        if relation_type.tag == "head-stem" and source in by_id:
            head_stems[source] = target
            head_sides[source] = relation_type.get("head-side", "")
        elif relation_type.tag == "beam-stem":
            stem_beams[target].add(source)
        elif relation_type.tag == "flag-stem":
            flag_shape = (
                elements[source].get("shape", "")
                if source in elements
                else ""
            )
            match = re.search(r"FLAG_(\d+)_", flag_shape)
            flag_count = int(match.group(1)) if match else 1
            stem_flags[target] = max(stem_flags[target], flag_count)
        elif relation_type.tag == "chord-stem":
            chord_stems[source] = target
        elif (
            relation_type.tag == "containment"
            and source in elements
            and elements[source].tag == "beam-group"
            and target in elements
            and elements[target].tag == "beam"
        ):
            beam_groups[target] = source

    for measure in system.findall("./part/measure"):
        # Measure and stack IDs overlap with IDs on voices and barlines.  Look
        # up the stack in its own collection; a global ID dictionary silently
        # returns a different element and loses every chord onset.
        stack = next(
            (
                candidate
                for candidate in system.findall("stack")
                if candidate.get("id") == measure.get("id")
            ),
            None,
        )
        if stack is None:
            continue
        slot_times = {
            slot.get("id", ""): Fraction(slot.get("time-offset", "0"))
            for slot in stack.findall("slot")
        }
        for voice in measure.findall("voice"):
            for entry in voice.findall("./slots/entry"):
                value = entry.find("value")
                if value is None or value.get("status") != "BEGIN":
                    continue
                onset = slot_times.get(entry.findtext("key", ""))
                if onset is not None:
                    chord_onsets[value.get("chord", "")] = onset

    head_dots = augmentation_dot_counts(system)
    for head in heads:
        stem_id = head_stems.get(head.source_id)
        side = head_sides.get(head.source_id)
        head.stem_direction = {"LEFT": "down", "RIGHT": "up"}.get(side)
        if stem_id is None:
            stem_tolerance = (
                18
                if head.shape == "NOTEHEAD_DIAMOND_FILLED"
                else 7
            )
            candidates = [
                stem
                for stem in stems
                if abs(stem[1] - head.x) <= stem_tolerance
                and stem[2] - 5 <= head.y <= stem[3] + 5
            ]
            if candidates:
                stem = min(candidates, key=lambda item: abs(item[1] - head.x))
                stem_id = stem[0]
                head.stem_direction = (
                    "down"
                    if abs(stem[2] - head.y) < abs(stem[3] - head.y)
                    else "up"
                )
                head.stem_x = stem[1]
        if stem_id:
            matched_stem = next(
                (stem for stem in stems if stem[0] == stem_id),
                None,
            )
            if matched_stem is not None:
                head.stem_x = matched_stem[1]
            chord_ids = [
                chord_id
                for chord_id, linked_stem in chord_stems.items()
                if linked_stem == stem_id
            ]
            known_onsets = {
                chord_onsets[chord_id]
                for chord_id in chord_ids
                if chord_id in chord_onsets
            }
            if len(known_onsets) == 1:
                head.time = known_onsets.pop()
                head.time_verified = True
            head.beam_count = len(stem_beams[stem_id])
            head.flag_count = stem_flags[stem_id]
            groups = sorted(
                {
                    beam_groups[beam_id]
                    for beam_id in stem_beams[stem_id]
                    if beam_id in beam_groups
                }
            )
            head.beam_group = groups[0] if len(groups) == 1 else None
        head.dots = head_dots[head.source_id]


def annotate_graphic_beams(
    image_path: Path,
    systems: list[ET.Element],
    systems_heads: list[list[Head]],
) -> None:
    """Recover beam groups missed by OMR from thick horizontal image strokes."""
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(image_path)
    binary = (image < 80).astype(np.uint8) * 255

    for system_index, (system, heads) in enumerate(
        zip(systems, systems_heads),
        1,
    ):
        if not heads:
            continue
        line_ys = [
            float(point.get("y"))
            for line in system.findall(".//line")
            for point in line.findall("point")
        ]
        if not line_ys:
            continue
        y0 = max(0, int(min(line_ys)) - 110)
        y1 = min(image.shape[0], int(max(line_ys)) + 100)
        roi = binary[y0:y1]
        opened = cv2.morphologyEx(
            roi,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (18, 2)),
        )
        contours, _ = cv2.findContours(
            opened,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        boxes = []
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            if width >= 30 and 5 <= height <= 20:
                boxes.append((x, y + y0, x + width, y + y0 + height))

        # A system with no detected beam candidates (for example a page that
        # only contains whole/half notes) is valid. Nothing to annotate here.
        if not boxes:
            continue

        groups: list[list[tuple[int, int, int, int]]] = []
        system_left = min(box[0] for box in boxes)
        system_right = max(box[2] for box in boxes)
        system_width = max(1, system_right - system_left)
        for box in sorted(boxes, key=lambda item: (item[0], item[1])):
            # Morphological opening also exposes full staff/system lines.
            # They must not become a beam spanning unrelated measures.
            if box[2] - box[0] > system_width * 0.55:
                continue
            for group in groups:
                if any(
                    not (box[2] < other[0] - 3 or box[0] > other[2] + 3)
                    and not (box[3] < other[1] - 5 or box[1] > other[3] + 5)
                    for other in group
                ):
                    group.append(box)
                    break
            else:
                groups.append([box])

        for group_index, group in enumerate(groups, 1):
            group_x0 = min(box[0] for box in group)
            group_x1 = max(box[2] for box in group)
            group_y = sum((box[1] + box[3]) / 2 for box in group) / len(group)
            members = []
            for head in heads:
                # A standalone flag already specifies the note value. Graphic
                # beam recovery is only for beamed stems and must never turn
                # an eighth-note kick into 16th note plus 16th rest.
                if head.beam_group is not None or head.flag_count:
                    continue
                if not (group_x0 - 12 <= head.x <= group_x1 + 12):
                    continue
                if not (10 < abs(group_y - head.y) < 110):
                    continue
                # A beam must lie beyond the notehead in the stem direction.
                # Without this check, an upper cymbal beam can be projected
                # onto a lower bass-drum head sharing the same x position.
                if head.stem_direction == "up" and group_y >= head.y:
                    continue
                if head.stem_direction == "down" and group_y <= head.y:
                    continue
                members.append(head)
            if len(members) < 2:
                continue
            group_id = f"graphic:{system_index}:{group_index}"
            for head in members:
                beam_count = 0
                for box in group:
                    if box[0] - 6 <= head.x <= box[2] + 6:
                        beam_count += 1
                if not beam_count:
                    continue
                head.beam_count = max(head.beam_count, beam_count)
                head.beam_group = group_id
                if head.stem_direction is None:
                    head.stem_direction = (
                        "up" if group_y < head.y else "down"
                    )


def note_duration(heads: list[Head]) -> str | None:
    """Infer the notated value from beams/flags and notehead fill."""
    if not heads:
        return None
    head = max(heads, key=lambda item: (item.beam_count, item.flag_count))
    subdivisions = max(head.beam_count, head.flag_count)
    if subdivisions >= 3:
        return "32nd"
    if subdivisions == 2:
        return "16th"
    if subdivisions == 1:
        return "eighth"
    if head.stem_direction is None:
        return "whole" if head.shape.endswith("_VOID") else "quarter"
    if head.shape.endswith("_VOID"):
        return "half"
    return "quarter"


def parse_articulations(system: ET.Element) -> list[Articulation]:
    result: list[Articulation] = []
    shape_map = {
        "ACCENT": "accent",
        "TENUTO": "tenuto",
    }
    for element in system.findall(".//articulation"):
        if element.find("bounds") is None:
            continue
        kind = shape_map.get(element.get("shape", ""))
        if kind is None:
            continue
        x, y, _, _ = bounds_center(element)
        result.append(Articulation(x=x, y=y, kind=kind))
    return result


def curve_is_plausible(
    left: "Head",
    right: "Head",
    chain: list[dict[str, object]],
) -> bool:
    """Reject curves that cannot be printed ties/slurs in this score family."""
    if left is right:
        return False
    if left.drum not in CURVE_DRUMS or right.drum not in CURVE_DRUMS:
        return False
    grade = max(float(segment.get("grade") or 0) for segment in chain)
    if grade < CURVE_MIN_GRADE:
        return False
    if (
        left.measure is not None
        and right.measure is not None
        and left.time is not None
        and right.time is not None
        and (right.measure, right.time) <= (left.measure, left.time)
    ):
        return False
    return True


def annotate_head_curves(
    systems: list[ET.Element],
    heads_by_system: list[list[Head]],
) -> dict[str, int]:
    """Resolve printed tie and slur endpoints to their drum heads.

    Audiveris attaches curved symbols to head IDs through ``slur-head``
    relations.  A real tie must connect the same drum; a curve between two
    different instruments is a phrase slur and must not alter duration.
    System-split curves are joined through their left/right extension IDs.
    """
    heads_by_id = {
        head.source_id: head
        for heads in heads_by_system
        for head in heads
    }
    endpoint_heads: dict[str, list[tuple[str, Head]]] = (
        collections.defaultdict(list)
    )
    for system in systems:
        for relation in system.findall(".//relation"):
            slur_head = relation.find("slur-head")
            if slur_head is None:
                continue
            head = heads_by_id.get(relation.get("target", ""))
            if head is not None:
                endpoint_heads[relation.get("source", "")].append(
                    (str(slur_head.get("side") or ""), head)
                )

    segments: dict[str, dict[str, object]] = {}
    for system in systems:
        for slur in system.findall(".//slur"):
            source_id = slur.get("id")
            if not source_id:
                continue
            segments[source_id] = {
                "id": source_id,
                "tie": slur.get("tie") == "true",
                "grade": float(
                    slur.get("grade") or slur.get("ctx-grade") or "0"
                ),
                "left-extension": slur.get("left-extension"),
                "right-extension": slur.get("right-extension"),
                "ctx-grade": float(slur.get("ctx-grade") or "0"),
                "endpoints": endpoint_heads.get(source_id, []),
            }

    def chains() -> list[list[dict[str, object]]]:
        visited: set[str] = set()
        result = []
        for source_id, segment in segments.items():
            left_extension = segment.get("left-extension")
            if left_extension in segments:
                continue
            chain = []
            current_id: str | None = source_id
            while current_id and current_id in segments:
                if current_id in visited:
                    break
                visited.add(current_id)
                current = segments[current_id]
                chain.append(current)
                right_extension = current.get("right-extension")
                current_id = (
                    str(right_extension)
                    if right_extension in segments
                    else None
                )
            if chain:
                result.append(chain)
        # Disconnected/cyclic extension fragments must still be visible to
        # the caller as unresolved instead of silently disappearing.
        for source_id, segment in segments.items():
            if source_id not in visited:
                result.append([segment])
        return result

    ties = 0
    slurs = 0
    unresolved = 0
    for chain in chains():
        left_heads = [
            head
            for segment in chain
            for side, head in segment["endpoints"]
            if side == "LEFT"
        ]
        right_heads = [
            head
            for segment in chain
            for side, head in segment["endpoints"]
            if side == "RIGHT"
        ]
        if len(left_heads) != 1 or len(right_heads) != 1:
            unresolved += 1
            continue
        left = left_heads[0]
        right = right_heads[0]
        if left is right:
            unresolved += 1
            continue
        if not curve_is_plausible(left, right, chain):
            continue
        curve_id = "|".join(str(segment.get("id") or "") for segment in chain)
        same_instrument = (
            left.drum is not None
            and left.drum == right.drum
            and left.pitch_position == right.pitch_position
        )
        wants_tie = any(bool(segment.get("tie")) for segment in chain)
        if wants_tie and not same_instrument:
            # Audiveris occasionally labels a phrase curve as a tie.  Different
            # drum positions cannot sustain one another, so downgrade it.
            wants_tie = False
        if wants_tie and same_instrument:
            left.tie_start = curve_id
            right.tie_end = curve_id
            ties += 1
            continue
        left.slur_starts.append(curve_id)
        right.slur_ends.append(curve_id)
        slurs += 1
    return {
        "ties": ties,
        "slurs": slurs,
        "unresolved": unresolved,
    }


def template_matches(
    image: np.ndarray,
    template_path: Path,
    threshold: float,
    minimum_separation: float = 12.0,
) -> list[tuple[float, float, float]]:
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(template_path)
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= threshold)
    h, w = template.shape
    matches: list[tuple[float, float, float]] = []
    for y, x in sorted(
        zip(ys.tolist(), xs.tolist()),
        key=lambda point: float(result[point[0], point[1]]),
        reverse=True,
    ):
        cx = x + w / 2
        cy = y + h / 2
        score = float(result[y, x])
        if all(
            (cx - px) ** 2 + (cy - py) ** 2 > minimum_separation**2
            for px, py, _ in matches
        ):
            matches.append((cx, cy, score))
    return matches


def annotate_grace_notes_from_image(
    image_path: Path,
    systems_heads: list[list[Head]],
    small_head_template: Path,
) -> int:
    """Attach printed single or double grace noteheads to their main attack.

    Audiveris can omit a small chord entirely when a grace-note slash is
    connected to the notehead.  Once omitted, both the grace note and the
    beam relationship with the following attack are lost.  The printed small
    notehead is stable across the source book, so match it directly and attach
    every match to the nearest following upper-voice notehead on the same
    staff position.
    """
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(image_path)
    matches = template_matches(
        image,
        small_head_template,
        threshold=0.92,
        minimum_separation=8.0,
    )
    attached = 0
    for x, y, _ in matches:
        for heads in systems_heads:
            if not heads:
                continue
            min_y = min(head.y for head in heads) - 100
            max_y = max(head.y for head in heads) + 120
            if not min_y <= y <= max_y:
                continue
            if any(
                abs(head.x - x) <= 8 and abs(head.y - y) <= 8
                for head in heads
            ):
                break
            targets = [
                head
                for head in heads
                if head.drum in UPPER_DRUMS
                and 12 <= head.x - x <= 105
                and abs(head.y - y) <= 12
            ]
            if not targets:
                break
            target = min(targets, key=lambda head: head.x - x)
            if not any(
                abs(grace.x - x) <= 2 and abs(grace.y - y) <= 2
                for grace in target.graces
            ):
                target.graces.append(
                    GraceSymbol(x=x, y=y, drum=int(target.drum))
                )
                target.graces.sort(key=lambda grace: grace.x)
                attached += 1
            break
    return attached


def annotate_open_hihats_from_circles(
    image: np.ndarray,
    systems_heads: list[list[Head]],
) -> int:
    """Map a small hollow circle above a hi-hat to Open Hi-Hat (pitch 46)."""
    binary = (image < 128).astype(np.uint8) * 255
    contours, _ = cv2.findContours(
        binary,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    changed = 0
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if not (10 <= width <= 30 and 10 <= height <= 30):
            continue
        if not (0.7 <= width / height <= 1.4):
            continue
        if not (70 <= cv2.contourArea(contour) <= 500):
            continue
        circle_x = x + width / 2
        circle_y = y + height / 2
        candidates = [
            head
            for heads in systems_heads
            for head in heads
            if head.drum == 42
            and abs(head.x - circle_x) <= 12
            and 45 <= head.y - circle_y <= 105
        ]
        if not candidates:
            continue
        selected = min(candidates, key=lambda head: abs(head.x - circle_x))
        selected.drum = 46
        changed += 1
    return changed


def annotate_diamond_rides_from_image(
    image: np.ndarray,
    systems_heads: list[list[Head]],
) -> int:
    """Distinguish hollow Ride diamonds from filled Ride Bell diamonds."""
    changed = 0
    for heads in systems_heads:
        for head in heads:
            if head.shape != "NOTEHEAD_DIAMOND_FILLED":
                continue
            x, y = round(head.x), round(head.y)
            # Sample just inside the diamond above and below the staff line.
            patches = [
                image[y - 5 : y - 2, x - 3 : x + 4],
                image[y + 3 : y + 6, x - 3 : x + 4],
            ]
            if any(patch.size == 0 for patch in patches):
                continue
            dark = sum(int((patch < 128).sum()) for patch in patches)
            total = sum(patch.size for patch in patches)
            hollow = dark / total < 0.62
            target = 51 if hollow else 53
            if head.drum != target:
                head.drum = target
                changed += 1
    return changed


def augment_heads_from_templates(
    image_path: Path,
    systems_heads: list[list[Head]],
    ride_template: Path,
    crash_template: Path,
) -> None:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(image_path)

    ride_matches = template_matches(image, ride_template, threshold=0.80)
    for x, y, _ in ride_matches:
        for heads in systems_heads:
            if not heads:
                continue
            min_y = min(head.y for head in heads) - 80
            max_y = max(head.y for head in heads) + 100
            if min_y <= y <= max_y:
                existing = next(
                    (
                        head
                        for head in heads
                        if abs(head.x - x) <= 7 and abs(head.y - y) <= 7
                    ),
                    None,
                )
                if existing is not None:
                    existing.drum = 51
                    existing.shape = "NOTEHEAD_DIAMOND_FILLED"
                    break
                heads.append(
                    Head(
                        source_id=f"template:ride:{round(x)}:{round(y)}",
                        x=x,
                        y=y,
                        pitch_position=-4,
                        shape="NOTEHEAD_DIAMOND_FILLED",
                        drum=51,
                    )
                )
                break

    # Some hollow Ride diamonds touching a tom stem score around 0.74-0.79.
    # Accept that lower band only when the candidate is directly above an
    # already recognized upper-voice drum head. This recovers missing Ride
    # heads without treating arbitrary diamond-like page noise as cymbals.
    fallback_ride_matches = template_matches(
        image,
        ride_template,
        threshold=0.74,
    )
    for x, y, _ in fallback_ride_matches:
        for heads in systems_heads:
            if not heads:
                continue
            min_y = min(head.y for head in heads) - 80
            max_y = max(head.y for head in heads) + 100
            if not min_y <= y <= max_y:
                continue
            if any(
                abs(head.x - x) <= 7 and abs(head.y - y) <= 7
                for head in heads
            ):
                break
            anchor_heads = [
                head
                for head in heads
                if head.drum in UPPER_DRUMS
                and abs(head.x - x) <= 18
                and 12 <= head.y - y <= 36
            ]
            if not anchor_heads:
                break
            heads.append(
                Head(
                    source_id=f"template:ride:fallback:{round(x)}:{round(y)}",
                    x=x,
                    y=y,
                    pitch_position=-4,
                    shape="NOTEHEAD_DIAMOND_FILLED",
                    drum=51,
                )
            )
            break

    # The small hollow circle above a hi-hat means Open Hi-Hat. Template
    # matching is too sensitive to page-specific antialiasing, so use closed
    # circular contours constrained by their geometric relation to a hi-hat.
    annotate_open_hihats_from_circles(image, systems_heads)

    crash_matches = template_matches(image, crash_template, threshold=0.72)
    for x, y, _ in crash_matches:
        for heads in systems_heads:
            if not heads:
                continue
            min_y = min(head.y for head in heads) - 80
            max_y = max(head.y for head in heads) + 100
            if min_y <= y <= max_y:
                existing = next(
                    (
                        head
                        for head in heads
                        if abs(head.x - x) <= 7 and abs(head.y - y) <= 7
                    ),
                    None,
                )
                if existing is not None:
                    existing.drum = 49
                    existing.shape = "NOTEHEAD_CROSS"
                    break
                heads.append(
                    Head(
                        source_id=f"template:crash:{round(x)}:{round(y)}",
                        x=x,
                        y=y,
                        pitch_position=-6,
                        shape="NOTEHEAD_CROSS",
                        drum=49,
                    )
                )
                break

    annotate_diamond_rides_from_image(image, systems_heads)


def discard_time_signature_false_heads(
    systems_measures: list[list[Measure]],
    systems_heads: list[list[Head]],
    lengths: dict[int, int],
) -> int:
    """Remove void heads produced by staff-leading meter glyphs.

    Audiveris frequently classifies the closed bowl of a printed ``3`` or
    ``4`` meter digit as a half-note head.  Meter glyphs sit immediately after
    the leading barline, unlike drum noteheads.
    """
    discarded = 0
    for measures, heads in zip(systems_measures, systems_heads):
        if not measures:
            continue
        kept = []
        for head in heads:
            measure = next(
                (
                    candidate
                    for candidate in measures
                    if candidate.left <= head.x <= candidate.right
                ),
                None,
            )
            if measure is None:
                kept.append(head)
                continue
            beats = lengths.get(measure.number)
            previous_beats = lengths.get(measure.number - 1)
            in_inline_meter = (
                beats is not None
                and previous_beats is not None
                and beats != previous_beats
            )
            limit = measure.left + (70 if in_inline_meter else 28)
            if (
                head.shape == "NOTEHEAD_VOID"
                and head.x <= limit
                and head.drum in {43, 48}
            ):
                discarded += 1
                continue
            if (
                in_inline_meter
                and head.x <= measure.left + 40
                and head.drum in {49, 51, 53, 57}
            ):
                discarded += 1
                continue
            kept.append(head)
        heads[:] = kept
    return discarded


def assign_heads(
    systems_measures: list[list[Measure]],
    system_heads: Iterable[list[Head]],
) -> None:
    for measures, heads in zip(systems_measures, system_heads):
        for head in heads:
            matches = [measure for measure in measures if measure.left <= head.x <= measure.right]
            if not matches:
                continue
            measure = matches[0]
            head.measure = measure.number
            if head.time_verified:
                continue
            if not measure.slots:
                continue
            local_x = head.x - measure.left
            slot = min(measure.slots, key=lambda candidate: abs(candidate.x - local_x))
            head.time = slot.time
            head.slot_error = abs(slot.x - local_x)


def assign_rests(
    systems_measures: list[list[Measure]],
    system_rests: Iterable[list[RestSymbol]],
) -> None:
    for measures, rests in zip(systems_measures, system_rests):
        for rest in rests:
            matches = [
                measure
                for measure in measures
                if measure.left <= rest.x <= measure.right
            ]
            if not matches:
                rest.review = True
                continue
            measure = matches[0]
            rest.measure = measure.number
            if not measure.slots:
                rest.review = True
                continue
            local_x = rest.x - measure.left
            slot = min(
                measure.slots,
                key=lambda candidate: abs(candidate.x - local_x),
            )
            rest.time = slot.time
            rest.slot_error = abs(slot.x - local_x)
            rest.review = rest.slot_error > 12


def apply_system_splits(
    systems_measures: list[list[Measure]],
    splits: list[tuple[int, float]],
) -> None:
    for split_number, split_x in sorted(splits, reverse=True):
        for system_measures in systems_measures:
            for index, measure in enumerate(system_measures):
                if measure.number != split_number:
                    continue
                split_measure(system_measures, index, split_x)
                break
            else:
                continue
            break
        else:
            raise ValueError(f"Split target measure {split_number} was not found")


def renumber(systems_measures: list[list[Measure]]) -> list[Measure]:
    measures = [measure for system in systems_measures for measure in system]
    for number, measure in enumerate(measures, 1):
        measure.number = number
    return measures


def annotate_repeats(
    systems_measures: list[list[Measure]],
    systems: list[ET.Element],
) -> None:
    """Recover repeat barlines from Audiveris structure, with guarded fallback."""
    measures = [measure for system in systems_measures for measure in system]
    for measure in measures:
        measure.start_repeat = False
        measure.end_repeat = False
        measure.repeat_count = 2

    for system_measures, system in zip(systems_measures, systems):
        for stack in system.findall("stack"):
            repeat = stack.get("repeat")
            if repeat not in {"LEFT", "RIGHT"}:
                continue
            count = 2
            for key in ("repeat-count", "repeatCount", "times", "count"):
                value = stack.get(key)
                if value:
                    try:
                        count = max(2, int(value))
                    except ValueError:
                        pass
                    break
            if repeat == "LEFT":
                boundary = float(stack.get("left", "0"))
                target = min(
                    system_measures,
                    key=lambda candidate: abs(candidate.left - boundary),
                    default=None,
                )
                if target is not None and abs(target.left - boundary) <= 2:
                    target.start_repeat = True
                    target.repeat_count = count
            else:
                boundary = float(stack.get("right", "0"))
                target = min(
                    system_measures,
                    key=lambda candidate: abs(candidate.right - boundary),
                    default=None,
                )
                if target is not None and abs(target.right - boundary) <= 2:
                    target.end_repeat = True
                    target.repeat_count = count

    # Older Audiveris outputs omit the stack attribute but still expose repeat
    # dots.  Lines alone are ambiguous with final barlines, so the fallback is
    # enabled only where an actual repeat-dot symbol exists nearby.
    for system_measures, system in zip(systems_measures, systems):
        repeat_dot_xs = []
        for element in system.findall(".//repeat-dot"):
            bounds = element.find("bounds")
            if bounds is not None:
                repeat_dot_xs.append(
                    float(bounds.get("x")) + float(bounds.get("w")) / 2
                )
        if not repeat_dot_xs:
            continue
        bars = []
        for element in system.findall(".//barline"):
            if element.find("bounds") is None:
                continue
            x, _, width, _ = bounds_center(element)
            shape = element.get("shape", "")
            if shape in {"THIN_BARLINE", "THICK_BARLINE"}:
                bars.append((x, shape, width))
        bars.sort()
        for left, right in zip(bars, bars[1:]):
            if right[0] - left[0] > 30:
                continue
            if left[1] == "THICK_BARLINE" and right[1] == "THIN_BARLINE":
                boundary = (left[0] + right[0]) / 2
                if not any(
                    boundary - 25 <= x <= boundary + 90
                    for x in repeat_dot_xs
                ):
                    continue
                target = min(
                    system_measures,
                    key=lambda measure: abs(measure.left - boundary),
                )
                if abs(target.left - boundary) <= 25:
                    target.start_repeat = True
            elif left[1] == "THIN_BARLINE" and right[1] == "THICK_BARLINE":
                boundary = (left[0] + right[0]) / 2
                if not any(
                    boundary - 90 <= x <= boundary + 25
                    for x in repeat_dot_xs
                ):
                    continue
                target = min(
                    system_measures,
                    key=lambda measure: abs(measure.right - boundary),
                )
                if abs(target.right - boundary) <= 25:
                    target.end_repeat = True


def annotate_endings(
    systems_measures: list[list[Measure]],
    systems: list[ET.Element],
) -> None:
    all_measures = [measure for measures in systems_measures for measure in measures]
    all_indexes = {id(measure): index for index, measure in enumerate(all_measures)}
    endings_by_group: collections.Counter[int] = collections.Counter()
    boundary_tolerance = 4.0

    for measures, system in zip(systems_measures, systems):
        endings = []
        for element in system.findall(".//ending"):
            bounds = element.find("bounds")
            if bounds is None:
                continue
            x = float(bounds.get("x"))
            width = float(bounds.get("w"))
            endings.append((x, x + width))
        for start, end in sorted(endings):
            # Ending bounds often touch the previous measure's right barline by
            # one pixel. Resolve the start against an actually covered span,
            # preferring an exact measure-left boundary.
            start_index = next(
                (
                    index
                    for index, measure in enumerate(measures)
                    if abs(measure.left - start) <= boundary_tolerance
                ),
                None,
            )
            if start_index is None:
                start_index = next(
                    (
                        index
                        for index, measure in enumerate(measures)
                        if min(measure.right, end) - max(measure.left, start)
                        > boundary_tolerance
                    ),
                    None,
                )
            if start_index is None:
                continue
            end_index = max(
                (
                    index
                    for index in range(start_index, len(measures))
                    if min(measures[index].right, end)
                    - max(measures[index].left, start)
                    > boundary_tolerance
                ),
                default=start_index,
            )
            covered = measures[start_index : end_index + 1]
            covered_absolute_start = all_indexes[id(covered[0])]
            # Ending numbers belong to the nearest preceding repeat section.
            # Coordinates restart on every system, so matching by x alone
            # across the page would merge unrelated repeats.
            group_index = max(
                (
                    index
                    for index in range(covered_absolute_start)
                    if all_measures[index].start_repeat
                ),
                default=-1,
            )
            group_key = (
                all_measures[group_index].number
                if group_index >= 0
                else 0
            )
            endings_by_group[group_key] += 1
            number = endings_by_group[group_key]
            for measure in covered:
                measure.volta = number


def detect_tuplets(
    systems_measures: list[list[Measure]],
    systems: list[ET.Element],
) -> dict[int, int]:
    """Map printed tuplet brackets/tags to their containing measures."""
    result: dict[int, int] = collections.defaultdict(int)
    for measures, system in zip(systems_measures, systems):
        for element in system.findall(".//tuplet"):
            if element.find("bounds") is None:
                continue
            # Closed shapes on drum sheets are occasionally classified as a
            # triplet "3".  Real tuplet tokens in the reviewed source set have
            # grade >= 0.70 and context grade >= 0.85; the LATIN M69 eighth
            # rest was a 0.565/0.766 false positive and must not turn ordinary
            # eighth-note slots into 5/24 and 7/24.
            if (
                float(element.get("grade") or "0") < 0.70
                or float(element.get("ctx-grade") or "0") < 0.85
            ):
                continue
            x, _, _, _ = bounds_center(element)
            matches = [
                measure
                for measure in measures
                if measure.left <= x <= measure.right
            ]
            if len(matches) == 1:
                result[matches[0].number] += 1
    return dict(result)


def write_json(
    output_path: Path,
    title: str,
    tempo: float,
    measures: list[Measure],
    heads_by_measure: dict[int, list[Head]],
    rests_by_measure: dict[int, list[RestSymbol]],
    articulations_by_measure: dict[int, list[Articulation]],
    lengths: dict[int, int],
    tuplets_by_measure: dict[int, int],
) -> None:
    unknown = collections.Counter()
    payload = {
        "title": title,
        "tempo": tempo,
        "measure_count": len(measures),
        "unknown_heads": [],
        "measures": [],
    }
    for measure in measures:
        measure_heads = heads_by_measure.get(measure.number, [])
        has_upper_voice = any(
            head.drum in UPPER_DRUMS for head in measure_heads
        )
        has_lower_voice = any(
            head.drum in LOWER_DRUMS for head in measure_heads
        )
        has_double_voice = has_upper_voice and has_lower_voice
        grouped_heads: list[list[Head]] = []
        for head in sorted(measure_heads, key=lambda item: item.x):
            if head.drum is None:
                unknown[(head.pitch_position, head.shape)] += 1
                continue
            same_stem = (
                bool(grouped_heads)
                and head.stem_x is not None
                and grouped_heads[-1][-1].stem_x is not None
                and abs(head.stem_x - grouped_heads[-1][-1].stem_x) <= 2
            )
            if (
                not grouped_heads
                or (
                    not same_stem
                    and head.x - grouped_heads[-1][-1].x
                    > ONSET_GROUP_X_TOLERANCE
                )
            ):
                grouped_heads.append([])
            grouped_heads[-1].append(head)

        normalized_events: list[dict[str, object]] = []
        for group in grouped_heads:
            for head in group:
                if has_double_voice and head.drum in LOWER_DRUMS:
                    head.stem_direction = "down"
                elif has_double_voice:
                    # Snare, toms, and cymbals share the upper voice.  In
                    # particular, simultaneous snare and cymbal hits share one
                    # stem and beam group.
                    head.stem_direction = "up"
            times = [head.time for head in group if head.time is not None]
            initial_time = min(times) if times else Fraction(0)
            center_x = sum(head.x for head in group) / len(group)
            articulations = sorted(
                {
                    articulation.kind
                    for articulation in articulations_by_measure.get(measure.number, [])
                    if abs(articulation.x - center_x) <= 12
                }
            )
            parts: list[dict[str, object]] = []
            parts_by_key: dict[tuple[str, str | None, int], list[Head]] = {}
            for head in group:
                direction = head.stem_direction or (
                    "up" if head.drum in UPPER_DRUMS else "down"
                )
                duration_type = note_duration([head])
                key = (direction, duration_type, head.dots)
                parts_by_key.setdefault(key, []).append(head)
            for (direction, duration_type, dots), part_heads in sorted(
                parts_by_key.items()
            ):
                parts.append(
                    {
                        "voice": direction,
                        "pitches": sorted(
                            {
                                head.drum
                                for head in part_heads
                                if head.drum is not None
                            }
                        ),
                        "duration": duration_type,
                        "dots": dots,
                        "beams": max(head.beam_count for head in part_heads),
                        "beam_group": next(
                            (
                                head.beam_group
                                for head in part_heads
                                if head.beam_group is not None
                            ),
                            None,
                        ),
                    }
                )
            graces = [
                {
                    "pitches": [grace.drum],
                    "kind": grace.kind,
                    "x": round(grace.x, 2),
                    "voice": (
                        head.stem_direction
                        or ("up" if head.drum in UPPER_DRUMS else "down")
                    ),
                }
                for head in group
                for grace in head.graces
            ]
            ties = sorted(
                {
                    (
                        "start" if head.tie_start else "end",
                        str(head.tie_start or head.tie_end or ""),
                        int(head.drum),
                    )
                    for head in group
                    if (
                        head.drum is not None
                        and (head.tie_start or head.tie_end)
                    )
                }
            )
            slurs = sorted(
                {
                    ("start", slur_id)
                    for head in group
                    for slur_id in head.slur_starts
                }
                | {
                    ("end", slur_id)
                    for head in group
                    for slur_id in head.slur_ends
                }
            )
            normalized_events.append(
                {
                    "time": str(initial_time),
                    "x": round(center_x, 2),
                    "rhythm_x": round(
                        sum(
                            head.stem_x
                            if head.stem_x is not None
                            else head.x
                            for head in group
                        )
                        / len(group),
                        2,
                    ),
                    "pitches": sorted({head.drum for head in group if head.drum is not None}),
                    "parts": parts,
                    "graces": graces,
                    "ties": [
                        {"role": role, "id": tie_id, "pitch": pitch}
                        for role, tie_id, pitch in ties
                    ],
                    "slurs": [
                        {"role": role, "id": slur_id}
                        for role, slur_id in slurs
                    ],
                    "articulations": articulations,
                    "review": any(
                        not head.time_verified
                        and head.slot_error is not None
                        and head.slot_error > 10
                        for head in group
                    ),
                    "time_verified": all(
                        head.time_verified for head in group
                        if head.time is not None
                    ),
                }
            )
        normalized_events.sort(key=lambda event: Fraction(event["time"]))
        normalized_rests = []
        seen_rests = set()
        for rest in rests_by_measure.get(measure.number, []):
            if rest.time is None:
                continue
            key = (
                rest.time,
                rest.voice,
                rest.duration_type,
                rest.dots,
            )
            if key in seen_rests:
                continue
            seen_rests.add(key)
            normalized_rests.append(
                {
                    "time": str(rest.time),
                    "x": round(rest.x, 2),
                    "voice": rest.voice,
                    "duration": rest.duration_type,
                    "dots": rest.dots,
                    "shape": rest.shape,
                    "pitch_position": round(rest.pitch_position, 3),
                    "review": rest.review,
                    "source": "audiveris-rest",
                }
            )
        rhythm_audit = normalize_measure_rhythm(
            normalized_events,
            normalized_rests,
            measure,
            lengths.get(measure.number, 4),
            lengths.get(measure.number - 1),
            bool(tuplets_by_measure.get(measure.number)),
        )
        payload["measures"].append(
            {
                "number": measure.number,
                "length": lengths.get(measure.number, 4),
                "system_start": measure.system_start,
                "start_repeat": measure.start_repeat,
                "end_repeat": measure.end_repeat,
                "repeat_count": measure.repeat_count,
                "volta": measure.volta,
                "events": normalized_events,
                "rests": normalized_rests,
                "rhythm_audit": rhythm_audit,
                "slots": [
                    {"x": round(slot.x, 3), "time": str(slot.time)} for slot in measure.slots
                ],
            }
        )
    payload["unknown_heads"] = [
        {
            "pitch_position": pitch_position,
            "shape": shape,
            "count": count,
        }
        for (pitch_position, shape), count in sorted(unknown.items())
    ]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if unknown:
        print("Unknown head mappings:")
        for key, count in sorted(unknown.items()):
            print(f"  {key}: {count}")


def retime_measure(
    measure: Measure,
    events: list[dict[str, object]],
    beats: int,
    tuplet: int | None,
) -> None:
    """Rebuild onset slots from horizontal spacing for an unclosed OMR bar."""
    if not events:
        return
    first_times = [
        Fraction(event["time"])
        for event in events
        if 0 <= Fraction(event["time"]) < 1
    ]
    first_time = first_times[0] if first_times else Fraction(0)
    candidates = [(beats * 4, 16)]
    if tuplet:
        candidates.insert(0, (beats * 6, 24))
    candidates.extend(
        [
            (beats * 8, 32),
        ]
    )

    for units, note_denominator in dict.fromkeys(candidates):
        if units < len(events):
            continue
        first_index = max(0, min(units - len(events), round(first_time * units)))
        px_unit = max(1.0, (measure.right - measure.left) / units)
        indexes = [first_index]
        for previous, current in zip(events, events[1:]):
            gap = float(current["x"]) - float(previous["x"])
            steps = max(1, round(gap / px_unit))
            indexes.append(indexes[-1] + steps)

        overflow = max(0, indexes[-1] - (units - 1))
        indexes = [max(0, index - overflow) for index in indexes]
        if all(current > previous for previous, current in zip(indexes, indexes[1:])):
            for event, index in zip(events, indexes):
                event["time"] = str(Fraction(index, note_denominator))
            return
    raise ValueError(f"Measure {measure.number}: could not infer a valid rhythm grid")


def clear_geometrically_confirmed_reviews(
    events: list[dict[str, object]],
) -> int:
    """Confirm stale slot warnings against the measure's onset line."""
    trusted = [
        event
        for event in events
        if not event.get("review") and Fraction(event["time"]) < 1
    ]
    if len(trusted) < 3:
        return 0

    times = [float(Fraction(event["time"])) for event in trusted]
    xs = [float(event.get("rhythm_x", event["x"])) for event in trusted]
    mean_time = sum(times) / len(times)
    mean_x = sum(xs) / len(xs)
    denominator = sum((time - mean_time) ** 2 for time in times)
    if denominator == 0:
        return 0
    slope = (
        sum((time - mean_time) * (x - mean_x) for time, x in zip(times, xs))
        / denominator
    )
    if slope <= 0:
        return 0
    intercept = mean_x - slope * mean_time

    cleared = 0
    for event in events:
        if not event.get("review") or Fraction(event["time"]) >= 1:
            continue
        predicted_x = intercept + slope * float(Fraction(event["time"]))
        if abs(predicted_x - float(event.get("rhythm_x", event["x"]))) <= 12:
            event["review"] = False
            event["review_resolution"] = "geometric-onset-fit"
            cleared += 1
    return cleared


def split_cross_voice_coincident_onsets(
    events: list[dict[str, object]],
    measure: Measure,
    beats: int,
) -> int:
    """Separate different voices that OMR incorrectly merged onto one slot.

    A snare/floor-tom chord and a following bass drum can be printed close
    together while still belonging to different eighth-note positions.  If
    two events have different voices, share one OMR onset, and their notehead
    centres are separated by roughly a quarter of a beat or more, the later
    notehead owns the next sixteenth-grid position rather than the same onset.
    """
    by_time: dict[Fraction, list[dict[str, object]]] = collections.defaultdict(list)
    for event in events:
        by_time[Fraction(str(event["time"]))].append(event)

    beat_width = max(1.0, (measure.right - measure.left) / beats)
    sixteenth_width = beat_width / 4
    changed = 0
    for time, coincident in by_time.items():
        if len(coincident) < 2:
            continue
        ordered = sorted(coincident, key=lambda event: float(event["x"]))
        for left, right in zip(ordered, ordered[1:]):
            left_voices = event_voice_directions(left)
            right_voices = event_voice_directions(right)
            if left_voices & right_voices:
                continue
            gap = float(right["x"]) - float(left["x"])
            if gap < beat_width * 0.18:
                continue
            step_count = max(1, round(gap / sixteenth_width))
            target = time + Fraction(step_count, 16)
            if target >= Fraction(beats, 4):
                continue
            if any(
                Fraction(str(event["time"])) == target
                and event_voice_directions(event) & right_voices
                for event in events
            ):
                continue
            right["time"] = str(target)
            right["review"] = False
            right["review_resolution"] = "cross-voice-onset-split"
            # Only the event that was displaced to the next eighth-note onset
            # needs its duration reduced.  The earlier event can legitimately
            # be a quarter-note snare/cymbal while the other voice plays the
            # off-beat eighth below it.
            if abs(gap - beat_width / 2) <= beat_width * 0.18:
                for part in right.get("parts") or []:
                    if part.get("duration") in {
                        "whole",
                        "half",
                        "quarter",
                    }:
                        part["duration"] = "eighth"
                        part["dots"] = 0
                        part["beams"] = max(1, int(part.get("beams") or 0))
            changed += 1
    events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def normalize_upper_eighth_beam_groups(
    events: list[dict[str, object]],
    measure_number: int,
    beats: int,
) -> int:
    """Connect two upper-voice eighth notes that share one beat.

    The source book beams upper-voice eighth-note pairs even when the pair
    changes instrument (for example Ride followed by a high tom).  A missing
    grace note or a low-confidence Ride head can otherwise make one of the two
    notes look like an isolated flagged eighth.
    """
    by_beat: dict[int, list[dict[str, object]]] = collections.defaultdict(list)
    for event in events:
        time = Fraction(str(event["time"]))
        if time.denominator & (time.denominator - 1):
            continue
        beat = int(time * 4)
        if beat < 0 or beat >= beats:
            continue
        if "up" in event_voice_directions(event):
            by_beat[beat].append(event)

    changed = 0
    for beat, members in by_beat.items():
        if len(members) != 2:
            continue
        if any(
            Fraction(str(current["time"])) - Fraction(str(previous["time"]))
            != Fraction(1, 8)
            for previous, current in zip(members, members[1:])
        ):
            continue
        eligible_parts = [
            part
            for event in members
            for part in (event.get("parts") or [])
            if str(part.get("voice") or "up") == "up"
            and str(part.get("duration")) == "eighth"
        ]
        if len(eligible_parts) < 2:
            continue
        group = f"upper:{measure_number}:{beat}"
        for part in eligible_parts:
            if part.get("beam_group") != group:
                part["beam_group"] = group
                changed += 1
            part["beams"] = max(1, int(part.get("beams") or 0))
    return changed


def normalize_beamed_group_timing(
    events: list[dict[str, object]],
    *,
    has_tuplet: bool = False,
    measure: Measure | None = None,
    beats: int | None = None,
) -> int:
    """Place members of one printed beam group on their cumulative durations.

    A beam group is one rhythmic unit.  Audiveris can give every member a
    plausible-looking but individually shifted slot, so lateral snapping must
    only choose the group's anchor.  Once the anchor is known, the printed
    note values determine every following onset.  A group ending on the final
    barline is anchored backwards from the bar end; this avoids collapsing the
    last compressed group onto the preceding sixteenth-note grid.
    """
    groups: dict[tuple[str, str], list[tuple[dict[str, object], dict]]] = (
        collections.defaultdict(list)
    )
    for event in events:
        for part in event.get("parts") or []:
            beam_group = part.get("beam_group")
            if beam_group:
                groups[(str(part.get("voice") or "up"), str(beam_group))].append(
                    (event, part)
                )

    proposals: dict[int, set[Fraction]] = collections.defaultdict(set)
    for members in groups.values():
        if len(members) < 2:
            continue
        if has_tuplet and len(members) >= 3:
            continue
        ordered = sorted(
            members,
            key=lambda item: (
                float(item[0]["x"]),
                float(Fraction(str(item[0]["time"]))),
            ),
        )
        start = Fraction(str(ordered[0][0]["time"]))
        valid = True
        durations: list[Fraction] = []
        total_duration = Fraction(0)
        for index, (event, part) in enumerate(ordered):
            duration_type = str(part.get("duration") or "")
            if duration_type not in NOTE_VALUE_FRACTIONS:
                valid = False
                break
            duration = NOTE_VALUE_FRACTIONS[duration_type]
            duration *= sum(
                Fraction(1, 2**power)
                for power in range(int(part.get("dots") or 0) + 1)
            )
            durations.append(duration)
            total_duration += duration
        if (
            valid
            and measure is not None
            and beats is not None
            and ordered
            and abs(float(ordered[-1][0]["x"]) - measure.right)
            <= max(12.0, (measure.right - measure.left) / 4 * 0.25)
        ):
            bar_end = Fraction(beats, 4)
            anchored_start = bar_end - total_duration
            if anchored_start >= 0:
                start = anchored_start
        if valid:
            cursor = start
            for index, (event, _) in enumerate(ordered):
                proposals[id(event)].add(cursor)
                cursor += durations[index]

    changed = 0
    for event in events:
        original_time = Fraction(str(event["time"]))
        if has_tuplet and original_time.denominator % 3 == 0:
            # A tuplet-compatible onset from OMR is already authoritative.
            # Ordinary eighth-note beam reconstruction must not shift an
            # inner triplet note (for example 7/24 -> 1/3).
            continue
        times = proposals.get(id(event), set())
        if len(times) != 1:
            continue
        normalized = next(iter(times))
        if original_time == normalized:
            continue
        event["time"] = str(normalized)
        event["review"] = False
        event["review_resolution"] = "beam-group-grid"
        changed += 1
    events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def normalize_sequential_beam_groups(
    events: list[dict[str, object]],
    *,
    has_tuplet: bool = False,
) -> int:
    """Carry a regular beamed rhythm across adjacent printed beam groups.

    Audiveris can split a continuous stream of eighth notes into several beam
    groups and assign a correct time to every group except the last one. In
    particular, the final group may be decoded from a 32nd-note grid even
    though its spacing is visibly identical to the preceding eighth notes.
    Rebuilding each group internally is not enough: the start of the next
    group must also follow the cumulative printed duration.

    Only tightly adjacent groups with identical note values are chained. A
    visible gap, a different note value, a tuplet, or a conflicting event
    starts a fresh sequence, so deliberate rests and syncopation remain
    untouched.
    """
    if has_tuplet or len(events) < 3:
        return 0

    proposals: dict[int, set[Fraction]] = collections.defaultdict(set)

    for voice in ("up", "down"):
        groups: dict[str, list[tuple[dict[str, object], dict]]] = (
            collections.defaultdict(list)
        )
        conflicting_events: set[int] = set()
        for event in events:
            matching = [
                part
                for part in (event.get("parts") or [])
                if str(part.get("voice") or "up") == voice
            ]
            if len(matching) != 1:
                continue
            part = matching[0]
            beam_group = part.get("beam_group")
            if not beam_group:
                continue
            group_key = str(beam_group)
            if any(
                member_event is event
                for member_event, _ in groups.get(group_key, [])
            ):
                conflicting_events.add(id(event))
                continue
            groups[group_key].append((event, part))

        printed_groups: list[
            tuple[list[tuple[dict, dict]], float, Fraction, int]
        ] = []
        for members in groups.values():
            if any(id(event) in conflicting_events for event, _ in members):
                continue
            ordered = sorted(
                members,
                key=lambda item: float(item[0]["x"]),
            )
            if len(ordered) < 2:
                continue
            duration_types = {
                str(part.get("duration") or "") for _, part in ordered
            }
            dot_counts = {int(part.get("dots") or 0) for _, part in ordered}
            if len(duration_types) != 1 or len(dot_counts) != 1:
                continue
            duration_type = next(iter(duration_types))
            dots = next(iter(dot_counts))
            if duration_type not in NOTE_VALUE_FRACTIONS:
                continue
            steps = [
                float(right[0]["x"]) - float(left[0]["x"])
                for left, right in zip(ordered, ordered[1:])
            ]
            positive_steps = [step for step in steps if step > 0]
            if not positive_steps:
                continue
            unit_x = sorted(positive_steps)[len(positive_steps) // 2]
            printed_groups.append(
                (
                    ordered,
                    unit_x,
                    NOTE_VALUE_FRACTIONS[duration_type]
                    * sum(
                        Fraction(1, 2**power)
                        for power in range(dots + 1)
                    ),
                    dots,
                )
            )

        printed_groups.sort(key=lambda item: float(item[0][0][0]["x"]))
        run: list[
            tuple[list[tuple[dict, dict]], float, Fraction, int]
        ] = []

        def flush_run() -> None:
            if len(run) < 2:
                run.clear()
                return
            cursor = Fraction(str(run[0][0][0][0]["time"]))
            for group, _, duration, _ in run:
                for event, _ in group:
                    proposals[id(event)].add(cursor)
                    cursor += duration
            run.clear()

        for group in printed_groups:
            if not run:
                run.append(group)
                continue
            previous_group = run[-1]
            previous_last = previous_group[0][-1][0]
            current_first = group[0][0][0]
            gap = float(current_first["x"]) - float(previous_last["x"])
            unit_x = min(previous_group[1], group[1])
            same_value = (
                previous_group[2] == group[2]
                and previous_group[3] == group[3]
            )
            if not same_value or not (
                unit_x * 0.55 <= gap <= unit_x * 1.75
            ):
                flush_run()
            run.append(group)
        flush_run()

    changed = 0
    for event in events:
        times = proposals.get(id(event), set())
        if len(times) != 1:
            continue
        normalized = next(iter(times))
        if Fraction(str(event["time"])) == normalized:
            continue
        event["time"] = str(normalized)
        event["review"] = False
        event["review_resolution"] = "sequential-beam-grid"
        changed += 1
    events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def normalize_regular_upper_sequence(
    events: list[dict[str, object]],
    measure: Measure,
    beats: int,
) -> tuple[int, bool]:
    """Restore a continuous upper-voice pulse from evenly spaced noteheads.

    This is primarily for Hi-Hat and Ride notation. Both use the same rhythm;
    only their notehead shape differs. Slanted beams can make stem x positions
    invalid for onset measurement, while the notehead centers remain exact.
    """
    upper_events = []
    for event in events:
        directions: set[str] = set()
        for part in event.get("parts") or []:
            if any(
                int(pitch) in UPPER_DRUMS
                for pitch in part.get("pitches", [])
            ):
                directions.add(str(part.get("voice") or "up"))
        if not directions:
            directions = {
                "up"
                for pitch in event.get("pitches", [])
                if int(pitch) in UPPER_DRUMS
            }
        if "up" in directions:
            upper_events.append(event)
    upper_events.sort(key=lambda event: float(event["x"]))
    if len(upper_events) < 5:
        return 0, False
    upper_times = [
        Fraction(str(event["time"]))
        for event in upper_events
    ]
    already_regular = (
        all((time * 8).denominator == 1 for time in upper_times)
        and all(
            current > previous
            for previous, current in zip(upper_times, upper_times[1:])
        )
    )
    changed = 0
    if not already_regular:
        # This normalizer is only for a continuous upper-voice pulse.  A
        # measure containing confirmed 16th-note attacks has a mixed rhythmic
        # grouping; flattening it would move valid notes.
        off_eighth_grid = [
            event
            for event in upper_events
            if (Fraction(str(event["time"])) * 8).denominator != 1
        ]
        sixteenth_indices = {
            round(Fraction(str(event["time"])) * 16)
            for event in upper_events
        }
        mixed_sixteenth_parities = len(
            {index % 2 for index in sixteenth_indices}
        ) > 1
        has_sub_eighth_values = any(
            str(part.get("duration") or "")
            in {"16th", "32nd", "64th"}
            for event in upper_events
            for part in (event.get("parts") or [])
        )
        if (
            len(off_eighth_grid) > 1
            and mixed_sixteenth_parities
            and has_sub_eighth_values
        ):
            return 0, False

        gaps = [
            float(right["x"]) - float(left["x"])
            for left, right in zip(upper_events, upper_events[1:])
        ]
        positive = [gap for gap in gaps if gap > 0]
        if len(positive) != len(gaps):
            return 0, False
        median_gap = sorted(positive)[len(positive) // 2]
        quarter_width = max(1.0, (measure.right - measure.left) / beats)
        ratio = median_gap / quarter_width
        if 0.35 <= ratio <= 0.68:
            unit = Fraction(1, 8)
        elif 0.20 <= ratio <= 0.36:
            unit = Fraction(1, 16)
        else:
            return 0, False
        target_gap = float(unit) * 4 * quarter_width
        steps: list[int] = []
        for gap in gaps:
            ratio_gap = gap / target_gap
            step = max(1, round(ratio_gap))
            # Engraved spacing varies around system starts.  The mixed-parity
            # guard above still protects genuine sixteenth-note figures.
            allowance = max(0.35, step * 0.25)
            if abs(ratio_gap - step) > allowance:
                return 0, False
            steps.append(step)

        first_time = Fraction(str(upper_events[0]["time"]))
        start = unit * round(first_time / unit)
        if start < 0 or start + unit * sum(steps) >= Fraction(beats, 4):
            return 0, False
        normalized = start
        for event, step in zip(upper_events, [0, *steps]):
            normalized += unit * step
            if Fraction(str(event["time"])) != normalized:
                event["time"] = str(normalized)
                changed += 1
            event["review"] = False
            event["review_resolution"] = "regular-upper-grid"

    ride_beats: collections.Counter[int] = collections.Counter(
        int(Fraction(str(event["time"])) * 4)
        for event in upper_events
        if 51 in {int(pitch) for pitch in event.get("pitches", [])}
    )
    for event in upper_events:
        if 51 not in {int(pitch) for pitch in event.get("pitches", [])}:
            continue
        beat = int(Fraction(str(event["time"])) * 4)
        group = (
            f"ride:{measure.number}:{beat}"
            if ride_beats[beat] >= 2
            else None
        )
        for part in event.get("parts") or []:
            if not any(
                int(pitch) in UPPER_DRUMS
                for pitch in part.get("pitches", [])
            ):
                continue
            part["duration"] = "eighth"
            part["dots"] = 0
            part["beams"] = 1
            part["beam_group"] = group
    events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed, True


def normalize_voice_pulse_sequences(
    events: list[dict[str, object]],
    measure: Measure,
    beats: int,
) -> int:
    """Recover a voice whose printed x spacing is a regular pulse.

    Audiveris can assign every attack to an internally valid slot while
    omitting a rest from its slot sequence.  The resulting voice is compressed:
    for example, Rock M29 has two eighths, an eighth rest, two more eighths,
    and a quarter hit, but every attack can be labelled as a continuous
    eighth-note run.  Off-beat bass-drum pulses can likewise become
    1/8, 5/16, 1/2, 3/4 instead of 1/8, 3/8, 5/8, 7/8.

    Notehead centres remain on the engraver's rhythmic x axis even when the
    OMR slots are wrong.  For each voice, accept a geometric sequence only when
    every adjacent gap is an integer multiple of a half beat.  Mixed or
    irregular phrases fail this check and are left untouched for visual
    review.
    """
    if len(events) < 3:
        return 0

    # Tuplets are explicit musical groupings and must not be quantized by the
    # ordinary binary-note pulse detector.
    if any(
        Fraction(str(event["time"])).denominator
        not in {1, 2, 4, 8, 16, 32, 64}
        for event in events
    ):
        return 0

    usable_left = measure.left + (110.0 if measure.system_start else 0.0)
    musical_width = measure.right - usable_left
    if musical_width <= 0:
        return 0
    half_beat_px = musical_width / (beats * 2)
    if half_beat_px <= 1:
        return 0

    proposals: dict[int, set[Fraction]] = collections.defaultdict(set)
    slot_locked_events: set[int] = set()
    quarter_width = max(1.0, (measure.right - measure.left) / beats)
    slot_tolerance = max(12.0, quarter_width * 0.16)
    for event in events:
        onset = Fraction(str(event["time"]))
        if not measure.slots:
            continue
        directions = event_voice_directions(event)
        previous_same_voice = [
            candidate
            for candidate in events
            if (
                candidate is not event
                and float(candidate["x"]) < float(event["x"])
                and directions & event_voice_directions(candidate)
            )
        ]
        if not previous_same_voice:
            continue
        previous_onset = Fraction(
            str(max(previous_same_voice, key=lambda item: float(item["x"]))["time"])
        )
        local_x = float(event["x"]) - measure.left
        slot = min(
            measure.slots,
            key=lambda candidate: abs(candidate.x - local_x),
        )
        previous_x = float(
            max(previous_same_voice, key=lambda item: float(item["x"]))["x"]
        )
        pulse_ratio = (float(event["x"]) - previous_x) / half_beat_px
        irregular_gap = abs(pulse_ratio - round(pulse_ratio)) > 0.18
        follows_beat = (previous_onset * 4).denominator == 1
        if (
            slot.time == onset
            and abs(slot.x - local_x) <= slot_tolerance
            and (irregular_gap or follows_beat)
        ):
            # A slot-and-geometry-confirmed attack outranks a coarser pulse
            # reconstruction when it does not form a regular off-beat pulse.
            # This protects true 7/16, 13/16 and 9/16 attacks while Rock M22's
            # four evenly spaced off-beat kicks remain eligible for recovery.
            slot_locked_events.add(id(event))

    for voice in ("up", "down"):
        voice_events = [
            event
            for event in events
            if voice in event_voice_directions(event)
        ]
        voice_events.sort(key=lambda event: float(event["x"]))
        # Three attacks are not enough evidence for a continuous pulse,
        # regardless of voice.  A sparse but valid phrase can otherwise be
        # pulled onto neighbouring eighth-note slots.  Require four anchors.
        if len(voice_events) < 4:
            continue

        gaps = [
            float(right["x"]) - float(left["x"])
            for left, right in zip(voice_events, voice_events[1:])
        ]
        if any(gap <= 0 for gap in gaps):
            continue

        steps: list[int] = []
        valid = True
        for gap in gaps:
            ratio = gap / half_beat_px
            step = max(1, round(ratio))
            allowance = max(0.22, step * 0.25)
            if abs(ratio - step) > allowance:
                valid = False
                break
            steps.append(step)
        if not valid:
            continue

        cumulative = Fraction(str(voice_events[0]["time"]))
        voice_times = [cumulative]
        for step in steps:
            cumulative += Fraction(step, 8)
            voice_times.append(cumulative)
        if any(time < 0 or time >= Fraction(beats, 4) for time in voice_times):
            continue

        for event, time in zip(voice_events, voice_times):
            proposals[id(event)].add(time)

    changed = 0
    for event in events:
        if id(event) in slot_locked_events:
            continue
        times = proposals.get(id(event), set())
        if len(times) != 1:
            continue
        normalized = next(iter(times))
        if Fraction(str(event["time"])) == normalized:
            continue
        event["time"] = str(normalized)
        event["review"] = False
        event["review_resolution"] = "voice-pulse-x-grid"
        changed += 1
    events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def snap_isolated_subdivision_noise(
    events: list[dict[str, object]],
    beats: int,
) -> int:
    """Remove one-off 32nd/64th noise from an otherwise standard voice.

    Audiveris occasionally emits values such as ``51/64`` or ``25/32`` for a
    single bass-drum attack surrounded entirely by eighth/16th notes.  A real
    rhythmic subdivision appears as a sequence, not as one isolated point.
    Snap only one noisy attack per voice, only when it is within half of a
    32nd note of the 16th grid.
    """
    directions = ("up", "down")
    changed = 0
    target = Fraction(beats, 4)
    for direction in directions:
        voice_events = [
            event
            for event in events
            if direction in event_voice_directions(event)
        ]
        noisy = [
            event
            for event in voice_events
            if Fraction(str(event["time"])).denominator > 16
        ]
        if len(noisy) != 1:
            continue
        event = noisy[0]
        current = Fraction(str(event["time"]))
        support = sorted(
            (
                float(other["x"]),
                Fraction(str(other["time"])),
            )
            for other in events
            if other is not event
        )
        event_x = float(event["x"])
        left = max(
            (item for item in support if item[0] < event_x),
            key=lambda item: item[0],
            default=None,
        )
        right = min(
            (item for item in support if item[0] > event_x),
            key=lambda item: item[0],
            default=None,
        )
        estimated = current
        if left is not None and right is not None and right[0] > left[0]:
            ratio = (event_x - left[0]) / (right[0] - left[0])
            estimated = left[1] + (right[1] - left[1]) * ratio
        if abs(estimated - current) > Fraction(3, 32):
            continue
        normalized = Fraction(round(estimated * 16), 16)
        if (
            normalized < 0
            or normalized >= target
            or abs(current - normalized) > Fraction(1, 32)
        ):
            continue
        event["time"] = str(normalized)
        event["review"] = False
        event["review_resolution"] = "isolated-grid-noise"
        changed += 1
    if changed:
        events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def normalize_sparse_lower_sixteenths(
    events: list[dict[str, object]],
    rests: list[dict[str, object]],
    measure: Measure,
    beats: int,
) -> int:
    """Normalize isolated off-beat bass-drum sixteenths.

    In sparse lower-voice writing, the source commonly uses:
    - a 16th rest followed by a dotted-eighth bass drum at ``beat + 1/16``;
    - a dotted-eighth rest followed by a 16th bass drum at ``beat + 3/16``.

    Audiveris can collapse either attack onto the beat boundary.  Detect the
    characteristic sparse sixteenth-grid pattern from the measure's noteheads,
    restore the attack position from the bar geometry, and emit the matching
    canonical rests instead of retaining slot noise.
    """
    lower_events = [
        event
        for event in events
        if "down" in event_voice_directions(event)
    ]
    if not lower_events:
        return 0
    if not any(
        Fraction(str(event["time"])).denominator > 8
        for event in lower_events
    ):
        return 0

    beat_width = max(1.0, (measure.right - measure.left) / beats)
    changed = 0
    sparse_beats: set[int] = set()
    for event in lower_events:
        current = Fraction(str(event["time"]))
        beat = int(current * 4)
        if beat <= 0:
            continue
        position = int((current - Fraction(beat, 4)) * 16)
        if position == 0:
            beat_slots = [
                slot
                for slot in measure.slots
                if slot.time == Fraction(beat, 4)
            ]
            later_slots = sorted(
                (
                    slot
                    for slot in measure.slots
                    if slot.time > Fraction(beat, 4)
                ),
                key=lambda slot: slot.time,
            )
            if beat_slots and later_slots:
                beat_slot = beat_slots[0]
                next_slot = later_slots[0]
                slot_steps = int(
                    (next_slot.time - beat_slot.time) * 16
                )
                if slot_steps > 0:
                    inferred_steps = round(
                        (float(event["x"]) - measure.left - beat_slot.x)
                        / ((next_slot.x - beat_slot.x) / slot_steps)
                    )
                    if inferred_steps in {1, 3}:
                        position = inferred_steps
        if position not in {1, 3}:
            continue
        normalized = Fraction(beat, 4) + Fraction(position, 16)
        if current != normalized:
            event["time"] = str(normalized)
            event["review"] = False
            event["review_resolution"] = "sparse-lower-sixteenth-grid"
            changed += 1
        for part in event.get("parts") or []:
            if str(part.get("voice") or "") != "down":
                continue
            if position == 1:
                part["duration"] = "eighth"
                part["dots"] = 1
            else:
                part["duration"] = "16th"
                part["dots"] = 0
            part["beams"] = 0
            part["beam_group"] = None
        sparse_beats.add(beat)

    if not sparse_beats:
        return changed

    kept_rests = []
    for rest in rests:
        beat = int(Fraction(str(rest["time"])) * 4)
        if str(rest.get("voice") or "up") == "down" and beat in sparse_beats:
            changed += 1
            continue
        kept_rests.append(rest)
    rests[:] = kept_rests

    for beat in sorted(sparse_beats):
        beat_positions = {
            int((Fraction(str(event["time"])) - Fraction(beat, 4)) * 16)
            for event in lower_events
            if int(Fraction(str(event["time"])) * 4) == beat
        }
        if beat_positions == {1}:
            rests.append(
                {
                    "time": str(Fraction(beat, 4)),
                    "x": round(measure.left + beat * beat_width, 2),
                    "voice": "down",
                    "duration": "16th",
                    "dots": 0,
                    "shape": "ONE_16TH_REST",
                    "pitch_position": 4.0,
                    "review": False,
                    "source": "sparse-sixteenth-pattern",
                    "review_resolution": "sparse-sixteenth-pattern",
                }
            )
        elif beat_positions == {3}:
            rests.append(
                {
                    "time": str(Fraction(beat, 4)),
                    "x": round(measure.left + beat * beat_width, 2),
                    "voice": "down",
                    "duration": "eighth",
                    "dots": 1,
                    "shape": "EIGHTH_REST",
                    "pitch_position": 4.0,
                    "review": False,
                    "source": "sparse-sixteenth-pattern",
                    "review_resolution": "sparse-sixteenth-pattern",
                }
            )
    events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def reconcile_sparse_lower_onset_alignment(
    events: list[dict[str, object]],
    rests: list[dict[str, object]],
) -> int:
    """Keep an upper attack aligned with a lower sparse-pattern rest.

    In sparse drum writing, a beat can begin with a lower-voice 16th rest
    while the upper voice attacks on the beat.  Audiveris may give those two
    symbols different times even though their printed x positions coincide.
    Left uncorrected, Rock M34 becomes ``3/16`` in the upper voice while the
    lower voice correctly starts at ``1/4``.  The geometry is decisive here:
    only an exact one-16th disagreement at the same printed position is
    repaired.
    """
    sparse_rests = [
        rest
        for rest in rests
        if (
            str(rest.get("voice") or "up") == "down"
            and str(rest.get("source") or "") == "sparse-sixteenth-pattern"
        )
    ]
    if not sparse_rests:
        return 0

    changed = 0
    for event in events:
        if "up" not in event_voice_directions(event):
            continue
        event_time = Fraction(str(event["time"]))
        matches = [
            rest
            for rest in sparse_rests
            if (
                abs(float(event["x"]) - float(rest["x"])) <= 2.0
                and Fraction(str(rest["time"])) != event_time
            )
        ]
        if len(matches) != 1:
            continue
        rest_time = Fraction(str(matches[0]["time"]))
        if abs(rest_time - event_time) != Fraction(1, 16):
            continue
        later_times = [
            Fraction(str(other["time"]))
            for other in events
            if Fraction(str(other["time"])) > event_time
        ]
        if later_times and rest_time >= min(later_times):
            # Never move an attack across the next event in the measure.
            continue
        event["time"] = str(rest_time)
        event["review"] = False
        event["review_resolution"] = "sparse-lower-onset-alignment"
        changed += 1

    if changed:
        events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def normalize_measure_rhythm(
    events: list[dict[str, object]],
    rests: list[dict[str, object]],
    measure: Measure,
    beats: int,
    previous_beats: int | None,
    has_tuplet: bool,
) -> dict[str, object]:
    """Run the reviewed rhythm arbitration passes in one fixed order.

    Geometry may be corrected by several independent signals.  Keeping the
    order explicit prevents an older fallback from undoing a newer,
    higher-confidence decision:

    1. separate voices incorrectly merged onto one onset;
    2. restore a regular upper-voice pulse;
    3. rebuild printed beam-group durations;
    4. repair the bar-wide horizontal 16th grid if still unsafe;
    5. align voice pulses, rests and sparse lower-voice sixteenths.
    """
    audit: dict[str, object] = {}
    audit["longRestStartsChanged"] = normalize_long_rest_starts(
        rests,
        measure,
        beats,
    )
    audit["restStartAnchoredOnsets"] = align_onsets_to_rest_starts(
        events,
        rests,
        beats,
    )
    audit["restEndAnchoredOnsets"] = align_onsets_to_rest_ends(
        events,
        rests,
        measure,
        beats,
    )
    audit["crossVoiceSplits"] = split_cross_voice_coincident_onsets(
        events,
        measure,
        beats,
    )

    regular_changed, regular_verified = normalize_regular_upper_sequence(
        events,
        measure,
        beats,
    )
    audit["regularUpperChanged"] = regular_changed
    audit["regularUpperVerified"] = regular_verified

    beam_group_changed = 0
    sequential_changed = 0
    sequential_verified = regular_verified
    if not regular_verified:
        beam_group_changed = normalize_beamed_group_timing(
            events,
            has_tuplet=has_tuplet,
            measure=measure,
            beats=beats,
        )
        sequential_changed = normalize_sequential_beam_groups(
            events,
            has_tuplet=has_tuplet,
        )
        sequential_verified = sequential_changed > 0
    audit["beamGroupChanged"] = beam_group_changed
    audit["sequentialBeamChanged"] = sequential_changed
    audit["sequentialBeamVerified"] = sequential_verified

    audit["upperBeamGroupsChanged"] = normalize_upper_eighth_beam_groups(
        events,
        measure.number,
        beats,
    )
    audit["closingBarlineClamped"] = clamp_out_of_range_events(events, beats)

    target = Fraction(beats, 4)
    duplicate_time_with_distance = any(
        Fraction(previous["time"]) == Fraction(current["time"])
        and abs(float(previous["x"]) - float(current["x"])) > 10
        and bool(
            event_voice_directions(previous)
            & event_voice_directions(current)
        )
        for previous, current in zip(events, events[1:])
    )
    has_thirty_second_position = any(
        Fraction(event["time"]).denominator > 16
        for event in events
    )
    all_event_times_verified = bool(events) and all(
        bool(event.get("time_verified"))
        for event in events
    )
    needs_bar_grid = (
        (
            measure.omr_duration != target
            and not all_event_times_verified
        )
        or has_thirty_second_position
        or any(Fraction(event["time"]) < 0 for event in events)
        or duplicate_time_with_distance
    )
    protected_by_sequence = (
        regular_verified
        or (
            sequential_verified
            and not has_thirty_second_position
            and all(Fraction(event["time"]) >= 0 for event in events)
            and not duplicate_time_with_distance
        )
    )
    audit["barGridRetimed"] = False
    if needs_bar_grid and not protected_by_sequence and not has_tuplet:
        try:
            audit["barGridRetimed"] = retime_from_horizontal_grid(
                measure,
                events,
                beats,
                previous_beats,
            )
            if not audit["barGridRetimed"]:
                retime_measure(
                    measure,
                    events,
                    beats,
                    None,
                )
                audit["barGridRetimed"] = "sparse-event-grid"
        except ValueError:
            for event in events:
                event["review"] = True
                event["review_resolution"] = "unresolved-rhythm-grid"
            audit["barGridRetimed"] = "unresolved"

    # A whole-bar horizontal fit is only an anchor correction.  Re-apply the
    # printed beam grouping afterwards so sixteenth/eighth mixtures inside a
    # beam are still governed by their drawn durations.  Without this pass,
    # Rock M68's mixed 16th-eighth-16th group is shifted member by member.
    audit["beamGroupAfterGrid"] = (
        normalize_beamed_group_timing(
            events,
            has_tuplet=has_tuplet,
            measure=measure,
            beats=beats,
        )
        if audit["barGridRetimed"]
        else 0
    )

    audit["geometricReviewsCleared"] = clear_geometrically_confirmed_reviews(
        events
    )
    audit["voicePulseChanged"] = normalize_voice_pulse_sequences(
        events,
        measure,
        beats,
    )
    # Voice-pulse recovery may move a member of a drawn beam group after the
    # first beam pass.  Rebuilding the group from its first confirmed onset
    # keeps the note-value sequence authoritative.  Rock M34's last group is
    # 16th + 16th + 8th, so its final Snare and Crash must not be split by an
    # intervening slot guess.
    audit["beamGroupFinal"] = normalize_beamed_group_timing(
        events,
        has_tuplet=has_tuplet,
        measure=measure,
        beats=beats,
    )
    audit["isolatedGridNoise"] = snap_isolated_subdivision_noise(
        events,
        beats,
    )
    audit["restsRetimed"] = retime_rests_from_events(
        events,
        rests,
        beats,
    )
    audit["sparseLowerChanged"] = normalize_sparse_lower_sixteenths(
        events,
        rests,
        measure,
        beats,
    )
    audit["sparseOnsetAligned"] = reconcile_sparse_lower_onset_alignment(
        events,
        rests,
    )
    rests.sort(
        key=lambda rest: (
            Fraction(str(rest["time"])),
            0 if rest["voice"] == "up" else 1,
        )
    )
    return audit


def retime_rests_from_events(
    events: list[dict[str, object]],
    rests: list[dict[str, object]],
    beats: int,
    *,
    use_geometry: bool = True,
) -> int:
    """Place recognized rests on the timing grid established by noteheads.

    Audiveris' rhythm slots can omit sixteenth-note and tuplet positions even
    when the printed heads are timed correctly.  Reusing those slots for rests
    puts an otherwise valid rest on top of a later note.  Build a local
    x-to-time mapping from trusted attacks instead and snap each rest's
    horizontal position to the nearest notated grid position.
    """
    trusted = [
        event
        for event in events
        if not event.get("review")
        and Fraction(str(event["time"])) < Fraction(beats, 4)
    ]

    # Rests and attacks in different voices can share one engraving column.
    # Audiveris may still assign the rest a neighbouring slot.  A near-exact
    # horizontal coincidence with one trusted attack is stronger evidence
    # than that slot, and is especially important for mirrored voices such as
    # a lower quarter rest beneath a beat-four drum chord.
    for rest in rests:
        if rest.get("review"):
            continue
        matches = {
            Fraction(str(event["time"]))
            for event in trusted
            if (
                str(event.get("review_resolution") or "")
                == "rest-end-anchor"
                and abs(float(event.get("x", 0)) - float(rest["x"])) <= 10
            )
        }
        if len(matches) != 1:
            continue
        aligned = next(iter(matches))
        if Fraction(str(rest["time"])) != aligned:
            rest["time"] = str(aligned)
            rest["review_resolution"] = "coincident-note-grid"

    # Use the attack position rather than a stem-derived x.  Rest glyphs are
    # centered on the same time axis as noteheads, while stems shift in a
    # direction that depends on the voice.
    points_by_x: dict[float, Fraction] = {}
    for event in trusted:
        x = float(event.get("x", event.get("rhythm_x", 0)))
        time = Fraction(str(event["time"]))
        points_by_x[x] = time
    points = sorted(points_by_x.items())
    has_x_grid = use_geometry and len(points) >= 3

    def raw_time_at(x: float) -> float | None:
        if x <= points[0][0]:
            left, right = points[0], points[1]
        elif x >= points[-1][0]:
            left, right = points[-2], points[-1]
        else:
            for left, right in zip(points, points[1:]):
                if left[0] <= x <= right[0]:
                    break
            else:
                return None
        span = right[0] - left[0]
        if span <= 0:
            return float(left[1])
        ratio = (x - left[0]) / span
        return float(left[1]) + ratio * float(right[1] - left[1])

    target = Fraction(beats, 4)
    event_rows: dict[
        str,
        list[tuple[Fraction, Fraction | None]],
    ] = {
        "up": [],
        "down": [],
    }
    for event in events:
        onset = Fraction(str(event["time"]))
        explicit_parts = {
            str(part.get("voice") or "up"): part
            for part in (event.get("parts") or [])
        }
        directions = set(explicit_parts)
        pitches = {int(pitch) for pitch in event.get("pitches", [])}
        if not directions:
            if pitches & UPPER_DRUMS:
                directions.add("up")
            if pitches & LOWER_DRUMS:
                directions.add("down")
        if not directions:
            directions.add("up")
        for direction in directions:
            part = explicit_parts.get(direction, {})
            duration_type = part.get("duration")
            duration: Fraction | None = None
            if duration_type in NOTE_VALUE_FRACTIONS:
                dots = int(part.get("dots") or 0)
                duration = NOTE_VALUE_FRACTIONS[str(duration_type)] * sum(
                    Fraction(1, 2**index)
                    for index in range(dots + 1)
                )
            event_rows[direction].append((onset, duration))

    events_by_voice: dict[str, list[tuple[Fraction, Fraction]]] = {
        "up": [],
        "down": [],
    }
    for direction, rows in event_rows.items():
        rows.sort(key=lambda row: row[0])
        for onset, duration in rows:
            # An event without a confirmed notated value is treated as a
            # point attack. Inferring a sustain from the next onset here would
            # make ordinary notation-overlay rests look invalid.
            if duration is None:
                duration = Fraction(0)
            events_by_voice[direction].append(
                (onset, onset + max(duration, Fraction(0)))
            )

    def duration_of(rest: dict[str, object]) -> Fraction:
        base = NOTE_VALUE_FRACTIONS.get(
            str(rest.get("duration")),
            Fraction(0),
        )
        dots = int(rest.get("dots") or 0)
        return base * sum(Fraction(1, 2**index) for index in range(dots + 1))

    def conflict_reason(
        rest: dict[str, object],
        onset: Fraction,
        duration: Fraction,
        accepted: dict[str, list[tuple[Fraction, Fraction]]],
    ) -> str | None:
        end = onset + duration
        if onset < 0:
            return "rest-before-bar"
        if duration <= 0 or end > target:
            return "rest-past-bar"
        voice = str(rest.get("voice") or "up")
        for event_start, event_end in events_by_voice[voice]:
            if (
                event_start == event_end
                and (
                    event_start == onset
                    or onset < event_start < end
                )
            ) or (
                event_start != event_end
                and onset < event_end
                and event_start < end
            ):
                return "rest-overlaps-voice-attack"
        for rest_start, rest_end in accepted[voice]:
            if onset < rest_end and rest_start < end:
                return "rest-overlaps-voice-rest"
        return None

    corrected = 0
    accepted_rests: dict[str, list[tuple[Fraction, Fraction]]] = {
        "up": [],
        "down": [],
    }
    overlay_rests: dict[str, list[tuple[Fraction, Fraction]]] = {
        "up": [],
        "down": [],
    }
    event_denominators = {
        Fraction(str(event["time"])).denominator
        for event in trusted
    }
    note_denominators = {8, 16, 32}
    if any(denominator % 3 == 0 for denominator in event_denominators):
        note_denominators.update({12, 24})
    if any(denominator >= 64 for denominator in event_denominators):
        note_denominators.add(64)
    for rest_index, rest in enumerate(rests):
        rest.pop("render_voice", None)
        voice = str(rest.get("voice") or "up")
        current_time = Fraction(str(rest["time"]))
        duration = duration_of(rest)
        current_conflict = conflict_reason(
            rest,
            current_time,
            duration,
            accepted_rests,
        )
        if current_conflict and int(rest.get("dots") or 0) > 0:
            duration_end = current_time + duration
            if duration_end <= target and all(
                current_time >= previous_end or duration_end <= previous_start
                for previous_start, previous_end in overlay_rests[voice]
            ):
                rest["render_voice"] = 2 if voice == "up" else 3
                rest["review"] = False
                rest["review_resolution"] = "augmentation-rest-overlay"
                overlay_rests[voice].append((current_time, duration_end))
                continue
            # A dot linked to the wrong glyph can make the displayed rest run
            # past the bar.  If the base note value fits exactly, reject the
            # impossible augmentation instead of emitting a clipped rest.
            original_dots = int(rest["dots"])
            rest["dots"] = 0
            undotted_duration = duration_of(rest)
            undotted_conflict = conflict_reason(
                rest,
                current_time,
                undotted_duration,
                accepted_rests,
            )
            if (
                current_time + undotted_duration <= target
                and undotted_conflict is None
            ):
                rest["review"] = False
                rest["review_resolution"] = "impossible-rest-dot-removed"
                accepted_rests[str(rest.get("voice") or "up")].append(
                    (current_time, current_time + undotted_duration)
                )
                continue
            if (
                current_time + undotted_duration <= target
                and all(
                    current_time >= previous_end
                    or current_time + undotted_duration <= previous_start
                    for previous_start, previous_end in overlay_rests[voice]
                )
            ):
                rest["render_voice"] = 2 if voice == "up" else 3
                rest["review"] = False
                rest["review_resolution"] = "impossible-rest-dot-overlay"
                overlay_rests[voice].append(
                    (current_time, current_time + undotted_duration)
                )
                continue
            rest["dots"] = original_dots
        if current_conflict is None:
            # Preserve a geometrically valid slot.  Only slots that collide
            # with an independently verified attack are retimed.
            rest["review"] = False
            if rest.get("review_resolution") in {
                "rest-overlaps-voice-attack",
                "rest-overlaps-voice-rest",
                "rest-past-bar",
            }:
                rest["review_resolution"] = "structure-confirmed"
            accepted_rests[str(rest.get("voice") or "up")].append(
                (current_time, current_time + duration)
            )
            continue

        raw_time = (
            raw_time_at(float(rest["x"]))
            if has_x_grid
            else None
        )
        if raw_time is None and has_x_grid:
            rest["review"] = True
            rest["review_resolution"] = "rest-time-unresolved"
            continue
        if raw_time is not None and (raw_time < 0 or raw_time >= float(target)):
            rest["review"] = True
            rest["review_resolution"] = current_conflict
            continue
        if raw_time is None:
            raw_time = float(current_time)

        candidates: set[Fraction] = set()
        for note_denominator in sorted(note_denominators):
            tick = round(raw_time * note_denominator)
            for delta in (-2, -1, 0, 1, 2):
                numerator = tick + delta
                if numerator < 0:
                    continue
                candidate = Fraction(numerator, note_denominator)
                if candidate < target:
                    candidates.add(candidate)
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                abs(float(candidate) - raw_time),
                abs(float(candidate - current_time)),
                candidate,
            ),
        )
        visual_candidate = next(
            (
                value
                for value in ordered
                if abs(float(value) - raw_time) <= 1 / 24
            ),
            None,
        )
        candidate = next(
            (
                value
                for value in ordered
                if abs(float(value) - raw_time) <= 1 / 24
                and conflict_reason(
                    rest,
                    value,
                    duration,
                    accepted_rests,
                )
                is None
            ),
            None,
        )
        if candidate is None:
            voice = str(rest.get("voice") or "up")
            fitting_overlay_candidates = [
                value
                for value in ordered
                if value + duration <= target
                and all(
                    value >= previous_end or value + duration <= previous_start
                    for previous_start, previous_end in overlay_rests[voice]
                )
            ]
            overlay_time = (
                fitting_overlay_candidates[0]
                if fitting_overlay_candidates
                else (
                    visual_candidate
                    if visual_candidate is not None
                    else current_time
                )
            )
            next_rest_start = next(
                (
                    Fraction(str(following["time"]))
                    for following in rests[rest_index + 1 :]
                    if str(following.get("voice") or "up") == voice
                ),
                None,
            )
            if (
                next_rest_start is not None
                and overlay_time + duration > next_rest_start
            ):
                aligned_time = next_rest_start - duration
                if aligned_time >= 0:
                    overlay_time = aligned_time
            duration_end = overlay_time + duration
            if duration_end <= target and all(
                overlay_time >= previous_end or duration_end <= previous_start
                for previous_start, previous_end in overlay_rests[voice]
            ):
                rest["time"] = str(overlay_time)
                rest["render_voice"] = 2 if voice == "up" else 3
                rest["review"] = False
                rest["review_resolution"] = "notation-overlay-voice"
                overlay_rests[voice].append((overlay_time, duration_end))
            else:
                rest["review"] = True
                rest["review_resolution"] = current_conflict
            continue
        rest["time"] = str(candidate)
        rest["review"] = False
        rest["review_resolution"] = "note-grid-retime"
        accepted_rests[str(rest.get("voice") or "up")].append(
            (candidate, candidate + duration)
        )
        corrected += 1
    rests.sort(
        key=lambda rest: (
            Fraction(rest["time"]),
            0 if rest["voice"] == "up" else 1,
        )
    )
    return corrected


def clamp_out_of_range_events(
    events: list[dict[str, object]],
    beats: int,
) -> int:
    """Keep attacks placed on Audiveris' closing barline inside the bar."""
    target = Fraction(beats, 4)
    clamped = 0
    for event in sorted(events, key=lambda item: float(item["x"])):
        if Fraction(str(event["time"])) < target:
            continue
        event["time"] = str(target - Fraction(1, 16))
        event["review"] = False
        event["review_resolution"] = "closing-barline-clamp"
        clamped += 1
    return clamped


def align_onsets_to_rest_ends(
    events: list[dict[str, object]],
    rests: list[dict[str, object]],
    measure: Measure,
    beats: int,
) -> int:
    """Use a complete printed rest as the anchor for its next attack.

    If OMR places a later chord inside a rest belonging to the same voice,
    moving that rest into an overlay voice preserves the wrong chord and
    duplicates the rest visually.  When the chord's notehead lies at the
    geometric end of the rest, the chord slot is the value that must move.
    """
    beat_width = max(1.0, (measure.right - measure.left) / beats)
    target = Fraction(beats, 4)
    changed = 0
    for rest in rests:
        if rest.get("review"):
            continue
        voice = str(rest.get("voice") or "up")
        start = Fraction(str(rest["time"]))
        duration_type = str(rest.get("duration") or "")
        duration = NOTE_VALUE_FRACTIONS.get(duration_type, Fraction(0))
        duration *= sum(
            Fraction(1, 2**power)
            for power in range(int(rest.get("dots") or 0) + 1)
        )
        end = start + duration
        if duration <= 0 or end >= target:
            continue
        following = sorted(
            (
                event
                for event in events
                if (
                    voice in event_voice_directions(event)
                    and float(event["x"]) > float(rest["x"]) + 8
                )
            ),
            key=lambda event: float(event["x"]),
        )
        if not following:
            continue
        event = following[0]
        current = Fraction(str(event["time"]))
        if not start < current < end:
            continue
        expected_x = (
            float(rest["x"])
            + float(duration) * beats * beat_width
        )
        if abs(float(event["x"]) - expected_x) > beat_width * 0.28:
            continue
        event["time"] = str(end)
        event["review"] = False
        event["review_resolution"] = "rest-end-anchor"
        changed += 1
    if changed:
        events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def align_onsets_to_rest_starts(
    events: list[dict[str, object]],
    rests: list[dict[str, object]],
    beats: int,
) -> int:
    """Align a note in the opposite voice with a longer rest onset.

    A half or quarter rest is printed as a beat-level anchor.  If an attack in
    the other voice shares that engraving column but OMR assigns it a later
    subdivision, the shared vertical position identifies the beat.  Rock M68
    uses this shape at beat 3: the lower half rest and upper tom are one
    column, while OMR labels the tom 5/8.
    """
    target = Fraction(beats, 4)
    changed = 0
    for rest in rests:
        if rest.get("review"):
            continue
        duration_type = str(rest.get("duration") or "")
        duration = NOTE_VALUE_FRACTIONS.get(duration_type, Fraction(0))
        if duration < Fraction(1, 4):
            continue
        start = Fraction(str(rest["time"]))
        if not Fraction(0) <= start < target:
            continue
        rest_voice = str(rest.get("voice") or "up")
        for event in events:
            if event.get("review"):
                continue
            if rest_voice in event_voice_directions(event):
                continue
            if abs(float(event["x"]) - float(rest["x"])) > 10:
                continue
            current = Fraction(str(event["time"]))
            if not start < current < start + duration:
                continue
            event["time"] = str(start)
            event["review"] = False
            event["review_resolution"] = "rest-start-anchor"
            changed += 1
    if changed:
        events.sort(key=lambda event: Fraction(str(event["time"])))
    return changed


def normalize_long_rest_starts(
    rests: list[dict[str, object]],
    measure: Measure,
    beats: int,
) -> int:
    """Keep half/whole rests on a musically complete onset boundary.

    Audiveris can assign a half rest to a nearby eighth-note slot because the
    slot table contains both voices.  A half rest cannot begin at 5/8 in a
    4/4 bar; its printed x position places it on beat 3.  Snapping only rests
    of at least half-note duration to integer multiples of their own duration
    avoids disturbing ordinary eighth/quarter rests.
    """
    width = measure.right - measure.left
    target = Fraction(beats, 4)
    if width <= 0:
        return 0
    changed = 0
    for rest in rests:
        if rest.get("review"):
            continue
        duration_type = str(rest.get("duration") or "")
        duration = NOTE_VALUE_FRACTIONS.get(duration_type, Fraction(0))
        duration *= sum(
            Fraction(1, 2**power)
            for power in range(int(rest.get("dots") or 0) + 1)
        )
        if duration < Fraction(1, 2):
            continue
        relative = (float(rest["x"]) - measure.left) / width
        steps = round(relative / float(duration))
        candidate = duration * max(0, steps)
        if candidate + duration > target:
            continue
        if Fraction(str(rest["time"])) != candidate:
            rest["time"] = str(candidate)
            rest["review_resolution"] = "long-rest-grid"
            changed += 1
    return changed


def event_voice_directions(event: dict[str, object]) -> set[str]:
    directions = {
        str(part.get("voice") or "up")
        for part in (event.get("parts") or [])
    }
    if directions:
        return directions
    pitches = {int(pitch) for pitch in event.get("pitches", [])}
    return {
        direction
        for direction, drum_set in (
            ("up", UPPER_DRUMS),
            ("down", LOWER_DRUMS),
        )
        if pitches & drum_set
    }


def retime_from_horizontal_grid(
    measure: Measure,
    events: list[dict[str, object]],
    beats: int,
    previous_beats: int | None,
) -> bool:
    """Align attacks to the bar-relative 16th/32nd-note geometry."""
    zero_slots = [slot for slot in measure.slots if slot.time == 0]
    if not events:
        return False
    fractions = [Fraction(event["time"]) for event in events]
    if any(
        fraction.denominator & (fraction.denominator - 1)
        for fraction in fractions
    ):
        return False

    # Audiveris commonly reports an extra beam line on drum noteheads.  For
    # image-originated drum charts the printed pulse grid in this converter is
    # a 16th-note grid; explicit tuplets are handled by retime_measure().
    grid_steps = beats * 4
    ordered = sorted(
        events,
        key=lambda item: float(item["x"]),
    )
    quarter_width = max(1.0, (measure.right - measure.left) / beats)
    slot_tolerance = max(10.0, quarter_width * 0.12)
    matched_slots = []
    for event in ordered:
        local_x = float(event["x"]) - measure.left
        slot = min(
            measure.slots,
            key=lambda candidate: abs(candidate.x - local_x),
            default=None,
        )
        if slot is None or abs(slot.x - local_x) > slot_tolerance:
            matched_slots = []
            break
        matched_slots.append(slot.time)
    if (
        len(matched_slots) == len(ordered)
        and all(
            Fraction(0) <= slot_time < Fraction(beats, 4)
            and slot_time.denominator <= 16
            for slot_time in matched_slots
        )
        and all(
            current > previous
            for previous, current in zip(matched_slots, matched_slots[1:])
        )
    ):
        for event, slot_time in zip(ordered, matched_slots):
            event["time"] = str(slot_time)
            event["review"] = False
            event["review_resolution"] = "confident-slot-grid"
        events.sort(key=lambda event: Fraction(str(event["time"])))
        return True

    # A system-start bar can expose two plausible origins: a time-zero slot
    # that includes the clef header, or the actual first printed attack.  A
    # fixed 110px clef offset made LATIN M77 and M105 start on 1/16 instead of
    # beat 1.  Evaluate every geometrically plausible origin against the whole
    # bar and select the lowest-error complete 16th-note assignment.
    candidates = [
        measure.left + slot.x
        for slot in zero_slots
    ]
    if previous_beats is not None and previous_beats != beats:
        candidates.append(measure.left + 70)
    if measure.system_start:
        candidates.append(measure.left + 110)
    candidates.append(measure.left + 44)
    origins = sorted({round(origin, 6) for origin in candidates})

    best: tuple[float, list[int], float] | None = None
    for origin in origins:
        scale = (measure.right - origin) / grid_steps
        if scale <= 0:
            continue
        indexes = []
        residual = 0.0
        ordering_penalty = 0.0
        valid = True
        for event in ordered:
            # Notehead centers lie on the rhythmic time axis. Stem x positions
            # lean under slanted beams and must not be used as onset positions.
            attack_x = float(event["x"])
            raw_index = math.floor((attack_x - origin) / scale + 0.5)
            residual += ((attack_x - origin) / scale - raw_index) ** 2
            index = max(0, min(grid_steps - 1, raw_index))
            if indexes and index <= indexes[-1]:
                index = indexes[-1] + 1
                ordering_penalty += 10.0
            if index >= grid_steps:
                valid = False
                break
            indexes.append(index)
        if not valid:
            continue
        score = residual / max(1, len(ordered)) + ordering_penalty
        origin_is_zero_slot = any(
            abs(origin - (measure.left + slot.x)) < 0.01
            for slot in zero_slots
        )
        first_grid_position = (float(ordered[0]["x"]) - origin) / scale
        if origin_is_zero_slot and abs(first_grid_position) <= 0.35:
            # A directly aligned time-zero slot is stronger evidence than a
            # small residual advantage from shifting the entire bar onto the
            # adjacent sixteenth grid.
            score -= 0.05
        if best is None or score < best[0]:
            best = (score, indexes, origin)
    if best is None:
        return False
    _, indexes, _ = best

    for event, index in zip(ordered, indexes):
        event["time"] = str(Fraction(index, 16))
        event["review"] = False
        event["review_resolution"] = "horizontal-16th-grid"
    events.sort(key=lambda event: Fraction(event["time"]))
    return True


def draw_review(
    image_path: Path,
    output_path: Path,
    systems: list[ET.Element],
    heads_by_system: list[list[Head]],
    rests_by_system: list[list[RestSymbol]],
) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    for system, heads, rests in zip(
        systems,
        heads_by_system,
        rests_by_system,
    ):
        stack_elements = system.findall("stack")
        for measure in stack_elements:
            left = float(measure.get("left"))
            top = image.height
            bottom = 0
            for line in system.findall(".//line"):
                for point in line.findall("point"):
                    y = float(point.get("y"))
                    top = min(top, y)
                    bottom = max(bottom, y)
            if bottom > top:
                draw.line((left, top - 10, left, bottom + 10), fill=(70, 70, 255), width=2)

        for head in heads:
            color = PITCH_COLORS.get(head.drum or -1, (255, 0, 255))
            radius = 6
            draw.ellipse(
                (
                    head.x - radius,
                    head.y - radius,
                    head.x + radius,
                    head.y + radius,
                ),
                outline=color,
                width=3,
            )
            if head.drum is not None:
                label = str(head.drum)
                draw.text((head.x + 7, head.y - 12), label, fill=color)
        for rest in rests:
            color = (30, 105, 210) if rest.voice == "up" else (205, 80, 20)
            draw.rectangle(
                (
                    rest.x - 12,
                    rest.y - 13,
                    rest.x + 12,
                    rest.y + 13,
                ),
                outline=color,
                width=2,
            )
            label = (
                ("U" if rest.voice == "up" else "L")
                + ":"
                + rest.duration_type
                + ("." * rest.dots)
            )
            draw.text((rest.x + 14, rest.y - 8), label, fill=color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def draw_measure_reviews(
    image_path: Path,
    output_dir: Path,
    systems_measures: list[list[Measure]],
    heads_by_system: list[list[Head]],
    rests_by_system: list[list[RestSymbol]],
    events_by_measure: dict[int, list[dict[str, object]]],
) -> None:
    image = Image.open(image_path).convert("RGB")
    output_dir.mkdir(parents=True, exist_ok=True)
    for measures, heads, rests in zip(
        systems_measures,
        heads_by_system,
        rests_by_system,
    ):
        ys = [head.y for head in heads]
        if not ys:
            continue
        y0 = max(0, int(min(ys)) - 75)
        y1 = min(image.height, int(max(ys)) + 45)
        for measure in measures:
            x0 = max(0, int(measure.left) - 12)
            x1 = min(image.width, int(measure.right) + 12)
            crop = image.crop((x0, y0, x1, y1))
            draw = ImageDraw.Draw(crop)
            for head in heads:
                if head.measure != measure.number:
                    continue
                px = head.x - x0
                py = head.y - y0
                color = PITCH_COLORS.get(head.drum or -1, (255, 0, 255))
                draw.ellipse((px - 6, py - 6, px + 6, py + 6), outline=color, width=3)
                events = events_by_measure.get(measure.number, [])
                event = (
                    min(events, key=lambda item: abs(float(item["x"]) - head.x))
                    if events
                    else None
                )
                if event is not None:
                    draw.text(
                        (px + 7, py - 13),
                        f"{head.drum}@{event['time']}",
                        fill=color,
                    )
            for rest in rests:
                if rest.measure != measure.number:
                    continue
                px = rest.x - x0
                py = rest.y - y0
                color = (30, 105, 210) if rest.voice == "up" else (205, 80, 20)
                draw.rectangle(
                    (px - 11, py - 12, px + 11, py + 12),
                    outline=color,
                    width=2,
                )
                draw.text(
                    (px + 13, py - 9),
                    (
                        ("U" if rest.voice == "up" else "L")
                        + ":"
                        + rest.duration_type
                        + ("." * rest.dots)
                    ),
                    fill=color,
                )
            crop = crop.resize((crop.width * 2, crop.height * 2))
            crop.save(output_dir / f"m{measure.number:02d}.png")


def parse_counts(value: str) -> list[int]:
    counts = [int(part) for part in value.replace(" ", "").split(",") if part]
    if not counts:
        raise argparse.ArgumentTypeError("counts must not be empty")
    return counts


def parse_splits(value: str) -> list[tuple[int, float]]:
    if not value:
        return []
    result = []
    for part in value.split(","):
        number, x = part.split(":")
        result.append((int(number), float(x)))
    return result


def parse_lengths(value: str) -> dict[int, int]:
    lengths: dict[int, int] = {}
    for part in value.split(","):
        if not part:
            continue
        numbers, beats_text = part.split(":")
        beats = int(beats_text)
        if beats not in (3, 4):
            raise argparse.ArgumentTypeError("Only 3/4 and 4/4 are supported")
        if "-" in numbers:
            start_text, end_text = numbers.split("-", 1)
            for number in range(int(start_text), int(end_text) + 1):
                lengths[number] = beats
        else:
            lengths[int(numbers)] = beats
    return lengths


def parse_tuplets(value: str) -> dict[int, int]:
    result: dict[int, int] = {}
    for part in value.split(","):
        if not part:
            continue
        measure_text, count_text = part.split(":")
        result[int(measure_text)] = int(count_text)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--omr", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-review", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--tempo", type=float, required=True)
    parser.add_argument(
        "--ride-template",
        type=Path,
        default=Path(__file__).parent / "templates" / "ride_diamond.png",
    )
    parser.add_argument(
        "--crash-template",
        type=Path,
        default=Path(__file__).parent / "templates" / "crash_cross.png",
    )
    parser.add_argument(
        "--small-grace-template",
        type=Path,
        default=Path(__file__).parent / "templates" / "small_drum_head.png",
    )
    parser.add_argument("--counts", type=parse_counts)
    parser.add_argument("--splits", type=parse_splits, default=[])
    parser.add_argument("--lengths", type=parse_lengths, default={})
    parser.add_argument("--tuplets", type=parse_tuplets, default={})
    args = parser.parse_args()

    root = read_omr_xml(args.omr)
    validate_drum_sheet(root)
    systems = root.findall("./page/system")
    systems_measures, systems = parse_stacks(root, args.counts)
    heads_by_system = [parse_heads(system) for system in systems]
    rests_by_system = [parse_rests(system) for system in systems]
    articulations_by_system = [
        parse_articulations(system) for system in systems
    ]
    discarded_heads = discard_time_signature_false_heads(
        systems_measures,
        heads_by_system,
        args.lengths,
    )
    augment_heads_from_templates(
        args.image,
        heads_by_system,
        args.ride_template,
        args.crash_template,
    )
    annotate_grace_notes_from_image(
        args.image,
        heads_by_system,
        args.small_grace_template,
    )
    curve_stats = annotate_head_curves(systems, heads_by_system)
    for system_index, (system, heads) in enumerate(
        zip(systems, heads_by_system),
        1,
    ):
        annotate_head_rhythm(system, heads)
        for head in heads:
            if head.beam_group is not None:
                head.beam_group = f"s{system_index}:{head.beam_group}"
    annotate_graphic_beams(
        args.image,
        systems,
        heads_by_system,
    )
    apply_system_splits(systems_measures, args.splits)
    measures = renumber(systems_measures)
    annotate_repeats(systems_measures, systems)
    annotate_endings(systems_measures, systems)
    assign_heads(systems_measures, heads_by_system)
    assign_rests(systems_measures, rests_by_system)
    detected_tuplets = detect_tuplets(systems_measures, systems)
    tuplets_by_measure = dict(detected_tuplets)
    tuplets_by_measure.update(args.tuplets)

    if args.counts is not None:
        expected = sum(args.counts)
        if len(measures) != expected:
            raise ValueError(
                f"Expected {expected} final measures, found {len(measures)}"
            )

    heads_by_measure: dict[int, list[Head]] = collections.defaultdict(list)
    for head in (head for heads in heads_by_system for head in heads):
        if head.measure is not None:
            heads_by_measure[head.measure].append(head)
    articulations_by_measure: dict[int, list[Articulation]] = collections.defaultdict(list)
    for system_measures, articulations in zip(
        systems_measures,
        articulations_by_system,
    ):
        for measure in system_measures:
            for articulation in articulations:
                if measure.left <= articulation.x <= measure.right:
                    articulations_by_measure[measure.number].append(articulation)
    rests_by_measure: dict[int, list[RestSymbol]] = collections.defaultdict(list)
    for rest in (rest for rests in rests_by_system for rest in rests):
        if rest.measure is not None:
            rests_by_measure[rest.measure].append(rest)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        args.output_json,
        args.title,
        args.tempo,
        measures,
        heads_by_measure,
        rests_by_measure,
        articulations_by_measure,
        args.lengths,
        tuplets_by_measure,
    )
    event_payload = json.loads(args.output_json.read_text(encoding="utf-8"))
    events_by_measure = {
        int(measure["number"]): measure["events"]
        for measure in event_payload["measures"]
    }
    draw_review(
        args.image,
        args.output_review,
        systems,
        heads_by_system,
        rests_by_system,
    )
    if args.review_dir:
        draw_measure_reviews(
            args.image,
            args.review_dir,
            systems_measures,
            heads_by_system,
            rests_by_system,
            events_by_measure,
        )

    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_review}")
    if args.review_dir:
        print(f"Wrote measure reviews to {args.review_dir}")
    print(f"Measures: {len(measures)}")
    print(f"Heads: {sum(len(heads) for heads in heads_by_system)}")
    if discarded_heads:
        print(f"Discarded meter-glyph false heads: {discarded_heads}")
    print(
        "Curves: "
        f"{curve_stats['ties']} ties, "
        f"{curve_stats['slurs']} slurs, "
        f"{curve_stats['unresolved']} unresolved"
    )


if __name__ == "__main__":
    main()
