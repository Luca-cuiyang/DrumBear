"""Shared structural validation for generated DB Score drum notation."""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from build_mscx import DRUMS, voice_event_details


DURATION_VALUES = {
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
}


@dataclass(frozen=True)
class VoiceTimingItem:
    element: ET.Element
    onset: Fraction
    duration: Fraction
    dots: int
    is_grace: bool


def read_voice_timing(
    voice: ET.Element,
    measure_length: int,
) -> tuple[list[VoiceTimingItem], Fraction]:
    """Read MSCX voice timing once for every structural validator."""
    cursor = Fraction(0)
    target = Fraction(measure_length)
    ratio = Fraction(1)
    tuplet_stack: list[Fraction] = []
    items: list[VoiceTimingItem] = []
    for element in list(voice):
        if cursor == target:
            break
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
        duration_type = element.findtext("durationType") or "quarter"
        duration = (
            target
            if duration_type == "measure"
            else DURATION_VALUES[duration_type]
        )
        dots = int(element.findtext("dots") or 0)
        if dots:
            duration *= sum(
                Fraction(1, 2**index)
                for index in range(dots + 1)
            )
        is_grace = (
            element.tag == "Chord"
            and (
                element.find("acciaccatura") is not None
                or element.find("appoggiatura") is not None
            )
        )
        items.append(
            VoiceTimingItem(
                element=element,
                onset=cursor,
                duration=duration,
                dots=dots,
                is_grace=is_grace,
            )
        )
        if not is_grace:
            cursor += duration * ratio
    return items, cursor


def expected_measure_lengths(payload: dict) -> dict[int, int]:
    return {
        int(measure["number"]): int(measure["length"])
        for measure in payload["measures"]
    }


def validate_mscx_child_order(mscx_path: Path) -> None:
    """Reject dotted chords/rests that DB Score would read undotted.

    MSCX deserialization is schema-order dependent. In DB Score's writer,
    ``dots`` precedes ``durationType`` inside both ``Chord`` and ``Rest``. A
    file with the reverse order opens, but the dot is silently ignored; the
    following attack then moves left by half of the base note value.
    """
    root = ET.parse(mscx_path).getroot()
    errors = []
    for element in root.findall(".//Chord") + root.findall(".//Rest"):
        dots = element.find("dots")
        duration_type = element.find("durationType")
        if dots is None or duration_type is None:
            continue
        children = list(element)
        if children.index(dots) > children.index(duration_type):
            errors.append(
                f"{element.tag} has durationType before dots"
            )
    if errors:
        raise RuntimeError(
            "MSCX child-order validation failed:\n"
            + "\n".join(errors[:20])
        )


def validate_no_unwanted_drum_articulations(mscx_path: Path) -> None:
    """Staccato marks are transcription noise in the current drum workflow."""
    root = ET.parse(mscx_path).getroot()
    unwanted = [
        subtype.text or ""
        for subtype in root.findall(".//Articulation/subtype")
        if "Staccato" in (subtype.text or "")
        or "Staccatissimo" in (subtype.text or "")
    ]
    if unwanted:
        raise RuntimeError(
            "Unexpected drum articulations: " + ", ".join(unwanted[:20])
        )


def validate_grace_structure(mscx_path: Path, payload: dict) -> None:
    """Require every reviewed grace note to survive in the native score.

    Grace chords occupy no rhythmic time.  They must appear immediately before
    their main chord, in source order, including repeated pitches in a double
    grace.  Comparing only the total note count would not catch a grace note
    attached to the wrong beat.
    """
    root = ET.parse(mscx_path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise RuntimeError("No drum staff found")
    measures = staff.findall("Measure")
    errors = []
    for measure, expected_measure in zip(measures, payload["measures"]):
        number = int(expected_measure["number"])
        details = voice_event_details(expected_measure)
        for voice_index, voice in enumerate(measure.findall("voice")):
            pending: list[tuple[list[int], str]] = []
            items, _ = read_voice_timing(
                voice,
                int(expected_measure["length"]),
            )
            for item in items:
                element = item.element
                if element.tag != "Chord":
                    continue
                pitches = sorted(
                    int(note.text)
                    for note in element.findall("Note/pitch")
                    if note.text is not None
                )
                if item.is_grace:
                    kind = (
                        "appoggiatura"
                        if element.find("appoggiatura") is not None
                        else "acciaccatura"
                    )
                    pending.append((pitches, kind))
                    continue

                expected_event = details.get(voice_index, {}).get(
                    round(item.onset * 960),
                    {},
                )
                wanted = [
                    (
                        sorted(int(pitch) for pitch in grace["pitches"]),
                        str(grace.get("kind") or "acciaccatura"),
                    )
                    for grace in expected_event.get("graces", [])
                ]
                if pending != wanted:
                    errors.append(
                        f"measure {number} voice {voice_index + 1} "
                        f"at {item.onset / 4}: grace notes {pending} != {wanted}"
                    )
                pending = []
            if pending:
                errors.append(
                    f"measure {number} voice {voice_index + 1}: "
                    f"orphan grace notes {pending}"
                )
    if errors:
        raise RuntimeError(
            "Grace-note validation failed:\n" + "\n".join(errors[:50])
        )


def validate_duration_map(mscx_path: Path, expected: dict[int, int]) -> list[str]:
    root = ET.parse(mscx_path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise RuntimeError("No drum staff found")
    measures = staff.findall("Measure")
    if len(measures) != len(expected):
        raise RuntimeError(f"Expected {len(expected)} measures, found {len(measures)}")

    errors = []
    for number, measure in enumerate(measures, 1):
        ends = []
        target = Fraction(expected[number])
        for voice in measure.findall("voice"):
            _, end = read_voice_timing(voice, expected[number])
            ends.append(end)
        if any(end != target for end in ends):
            errors.append(f"measure {number}: {ends}, expected {target}")
    return errors


def mscx_event_map(
    mscx_path: Path,
    expected: dict[int, int],
) -> dict[int, dict[Fraction, set[int]]]:
    root = ET.parse(mscx_path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise RuntimeError("No drum staff found")
    measures = staff.findall("Measure")
    if len(measures) != len(expected):
        raise RuntimeError(f"Expected {len(expected)} measures, found {len(measures)}")

    result: dict[int, dict[Fraction, set[int]]] = {}
    for number, measure in enumerate(measures, 1):
        events: dict[Fraction, set[int]] = {}
        for voice in measure.findall("voice"):
            items, _ = read_voice_timing(voice, expected[number])
            for item in items:
                element = item.element
                if element.tag != "Chord" or item.is_grace:
                    continue
                pitches = {
                    int(note.text)
                    for note in element.findall("Note/pitch")
                    if note.text is not None
                }
                if not pitches:
                    raise RuntimeError(
                        f"Measure {number}, voice: chord has no pitched notes"
                    )
                # Event JSON stores whole-note fractions (quarter = 1/4).
                events.setdefault(item.onset / 4, set()).update(pitches)
        result[number] = events
    return result


def expected_event_map(
    payload: dict,
) -> dict[int, dict[Fraction, set[int]]]:
    result: dict[int, dict[Fraction, set[int]]] = {}
    for measure in payload["measures"]:
        events: dict[Fraction, set[int]] = {}
        for event in measure["events"]:
            onset = Fraction(str(event["time"]))
            events.setdefault(onset, set()).update(
                int(pitch) for pitch in event["pitches"]
            )
        result[int(measure["number"])] = events
    return result


def validate_event_timeline(mscx_path: Path, payload: dict) -> None:
    expected_lengths = expected_measure_lengths(payload)
    actual = mscx_event_map(mscx_path, expected_lengths)
    expected = expected_event_map(payload)
    errors = []
    for number in expected_lengths:
        actual_events = actual[number]
        expected_events = expected[number]
        if actual_events != expected_events:
            missing = [
                (onset, pitches)
                for onset, pitches in sorted(expected_events.items())
                if actual_events.get(onset) != pitches
            ]
            extra = [
                (onset, pitches)
                for onset, pitches in sorted(actual_events.items())
                if expected_events.get(onset) != pitches
            ]
            errors.append(
                f"measure {number}: missing={missing[:4]} extra={extra[:4]}"
            )
    if errors:
        raise RuntimeError(
            "Event timeline validation failed:\n" + "\n".join(errors)
        )


def validate_score_structure(mscx_path: Path, payload: dict) -> None:
    root = ET.parse(mscx_path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise RuntimeError("No drum staff found")
    measures = staff.findall("Measure")
    payload_measures = payload["measures"]
    if len(measures) != len(payload_measures):
        raise RuntimeError(
            f"Expected {len(payload_measures)} measures, found {len(measures)}"
        )

    errors = []
    for number, (measure, expected) in enumerate(
        zip(measures, payload_measures),
        1,
    ):
        details = voice_event_details(expected)
        has_rest_overlay = any(
            rest.get("render_voice") is not None
            for rest in expected.get("rests", [])
        )
        expected_voices = 4 if has_rest_overlay else 1 + (1 if details[1] else 0)
        voices = measure.findall("voice")
        if len(voices) != expected_voices:
            errors.append(
                f"measure {number}: expected {expected_voices} voices, "
                f"found {len(voices)}"
            )

        for voice in voices:
            for chord in voice.findall("Chord"):
                pitches = [
                    int(note.text)
                    for note in chord.findall("Note/pitch")
                    if note.text is not None
                ]
                is_grace = (
                    chord.find("acciaccatura") is not None
                    or chord.find("appoggiatura") is not None
                )
                if not is_grace and 36 in pitches and expected_voices == 2:
                    if chord.findtext("StemDirection") != "down":
                        errors.append(
                            f"measure {number}: bass drum stem is not down"
                        )
                if (
                    not is_grace
                    and
                    expected_voices == 2
                    and any(
                        pitch in {42, 46, 49, 51, 53, 54, 55, 56, 57}
                        for pitch in pitches
                    )
                    and chord.findtext("StemDirection") != "up"
                ):
                    errors.append(
                        f"measure {number}: cymbal stem is not up"
                    )
                for note in chord.findall("Note"):
                    pitch_text = note.findtext("pitch")
                    if pitch_text is None:
                        continue
                    pitch = int(pitch_text)
                    expected_head = DRUMS[pitch][1]
                    actual_head = note.findtext("head") or "normal"
                    if actual_head != expected_head:
                        errors.append(
                            f"measure {number}: pitch {pitch} has notehead "
                            f"{actual_head}, expected {expected_head}"
                        )

    measure_eids = {measure.findtext("eid") for measure in measures}
    for volta in root.findall(".//SpannerMap/Volta"):
        for tag in ("startElement", "endElement"):
            reference = volta.findtext(tag)
            if reference not in measure_eids:
                errors.append(f"Volta has invalid {tag} reference")
    if errors:
        raise RuntimeError(
            "Score structure validation failed:\n" + "\n".join(errors)
        )


def mscx_rest_map(
    mscx_path: Path,
    expected: dict[int, int],
) -> dict[int, dict[tuple[Fraction, str, str, int], list[str]]]:
    root = ET.parse(mscx_path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise RuntimeError("No drum staff found")
    measures = staff.findall("Measure")
    result: dict[int, dict[tuple[Fraction, str, str, int], list[str]]] = {}
    for number, measure in enumerate(measures, 1):
        rests: dict[tuple[Fraction, str, str, int], list[str]] = {}
        for voice_index, voice in enumerate(measure.findall("voice")):
            items, _ = read_voice_timing(voice, expected[number])
            for item in items:
                element = item.element
                if element.tag != "Rest":
                    continue
                duration_type = element.findtext("durationType") or "quarter"
                key = (
                    item.onset / 4,
                    "up" if voice_index in {0, 2} else "down",
                    duration_type,
                    item.dots,
                )
                rests.setdefault(key, []).append(
                    element.findtext("visible") or "1"
                )
        result[number] = rests
    return result


def validate_rest_structure(mscx_path: Path, payload: dict) -> None:
    expected_lengths = expected_measure_lengths(payload)
    actual = mscx_rest_map(mscx_path, expected_lengths)
    errors = []
    for measure in payload["measures"]:
        number = int(measure["number"])
        available = dict(actual.get(number, {}))
        event_onsets = {
            Fraction(str(event["time"]))
            for event in measure.get("events", [])
        }
        for rest in measure.get("rests", []):
            if rest.get("review"):
                continue
            if Fraction(str(rest["time"])) in event_onsets:
                # A rest that shares an onset with an event is treated as a
                # visual overlay: the builder keeps the attack authoritative
                # and omits the rest, so it must not be required here.
                continue
            key = (
                Fraction(str(rest["time"])),
                str(rest.get("voice", "up")),
                str(rest.get("duration", "quarter")),
                int(rest.get("dots", 0)),
            )
            visibility = available.get(key)
            if not visibility:
                errors.append(f"measure {number}: missing rest {key}")
                continue
            expected_visibility = "0" if rest.get("hidden") else "1"
            if visibility.pop(0) != expected_visibility:
                errors.append(
                    f"measure {number}: recognized rest {key} has wrong visibility"
                )
    if errors:
        raise RuntimeError(
            "Rest structure validation failed:\n" + "\n".join(errors[:100])
        )


def validate_repeat_structure(mscx_path: Path, payload: dict) -> None:
    root = ET.parse(mscx_path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise RuntimeError("No drum staff found")
    measures = staff.findall("Measure")
    expected_measures = payload["measures"]
    errors = []
    for number, (actual, expected) in enumerate(
        zip(measures, expected_measures),
        1,
    ):
        actual_start = actual.find("startRepeat") is not None
        expected_start = bool(expected.get("start_repeat"))
        if actual_start != expected_start:
            errors.append(
                f"measure {number}: start repeat {actual_start} != {expected_start}"
            )
        actual_end_element = actual.find("endRepeat")
        actual_end = actual_end_element is not None
        expected_end = bool(expected.get("end_repeat"))
        if actual_end != expected_end:
            errors.append(
                f"measure {number}: end repeat {actual_end} != {expected_end}"
            )
        expected_count = max(2, int(expected.get("repeat_count", 2)))
        actual_count = (
            int(actual_end_element.text or "2")
            if actual_end_element is not None
            else expected_count
        )
        if actual_count != expected_count:
            errors.append(
                f"measure {number}: repeat count {actual_count} != {expected_count}"
            )

    expected_voltas = []
    group: list[dict] = []
    for measure in expected_measures:
        if measure.get("volta") is None:
            if group:
                expected_voltas.append(group)
                group = []
            continue
        if group and group[-1].get("volta") != measure.get("volta"):
            expected_voltas.append(group)
            group = []
        group.append(measure)
    if group:
        expected_voltas.append(group)

    measure_numbers = {
        measure.findtext("eid"): number
        for number, measure in enumerate(measures, 1)
    }
    actual_voltas = []
    for volta in root.findall(".//SpannerMap/Volta"):
        start = measure_numbers.get(volta.findtext("startElement"))
        end = measure_numbers.get(volta.findtext("endElement"))
        actual_voltas.append(
            (
                int(volta.findtext("beginText") or "0"),
                start,
                end,
                volta.find("endHookType") is not None,
            )
        )
    expected_volta_tuples = [
        (
            int(group[0]["volta"]),
            int(group[0]["number"]),
            int(group[-1]["number"]),
            bool(group[-1].get("end_repeat")),
        )
        for group in expected_voltas
    ]
    actual_voltas.sort(key=lambda item: (item[1] or 0, item[0]))
    if actual_voltas != expected_volta_tuples:
        errors.append(
            f"volta spans {actual_voltas} != {expected_volta_tuples}"
        )
    if errors:
        raise RuntimeError(
            "Repeat structure validation failed:\n" + "\n".join(errors[:100])
        )


def validate_curve_structure(mscx_path: Path, payload: dict) -> None:
    """Require every tie and phrase slur in the event map in the native score."""
    root = ET.parse(mscx_path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise RuntimeError("No drum staff found")
    note_info = {}
    chord_info = {}
    for number, (measure, measure_data) in enumerate(
        zip(staff.findall("Measure"), payload["measures"]),
        1,
    ):
        for voice_index, voice in enumerate(measure.findall("voice")):
            items, _ = read_voice_timing(voice, int(measure_data["length"]))
            for item in items:
                if item.element.tag != "Chord" or item.is_grace:
                    continue
                chord_eid = item.element.findtext("eid")
                if chord_eid:
                    chord_info[chord_eid] = (
                        number,
                        item.onset / 4,
                        voice_index,
                    )
                for note in item.element.findall("Note"):
                    note_eid = note.findtext("eid")
                    pitch_text = note.findtext("pitch")
                    if note_eid and pitch_text is not None:
                        note_info[note_eid] = (
                            number,
                            item.onset / 4,
                            voice_index,
                            int(pitch_text),
                        )

    actual_ties = set()
    for note_eid, note in (
        (element.findtext("eid"), element)
        for element in staff.findall(".//Note")
    ):
        if not note_eid:
            continue
        for tie in note.findall("Tie"):
            start_eid = tie.findtext("startElement")
            end_eid = tie.findtext("endElement")
            start = note_info.get(start_eid or "")
            end = note_info.get(end_eid or "")
            if start is None or end is None:
                raise RuntimeError(
                    f"Tie {tie.findtext('eid')} has dangling endpoints"
                )
            if start[3] != end[3]:
                raise RuntimeError(
                    f"Tie {tie.findtext('eid')} connects different pitches"
                )
            actual_ties.add(
                (start[0], str(start[1]), start[3], end[0], str(end[1]))
            )

    expected_ties = set()
    expected_slurs = set()
    tie_starts = {}
    slur_starts = {}
    for measure in payload["measures"]:
        number = int(measure["number"])
        for event in measure.get("events", []):
            onset = str(Fraction(str(event["time"])))
            for tie in event.get("ties", []):
                tie_id = str(tie.get("id") or "")
                role = str(tie.get("role") or "")
                pitch = int(tie.get("pitch") or 0)
                if role == "start":
                    tie_starts[(tie_id, pitch)] = (number, onset)
                elif role == "end":
                    start = tie_starts.get((tie_id, pitch))
                    if start is None:
                        raise RuntimeError(
                            f"Tie {tie_id} has no start endpoint"
                        )
                    expected_ties.add(
                        (
                            start[0],
                            start[1],
                            pitch,
                            number,
                            onset,
                        )
                    )
            for slur in event.get("slurs", []):
                slur_id = str(slur.get("id") or "")
                role = str(slur.get("role") or "")
                if role == "start":
                    slur_starts[slur_id] = (number, onset)
                elif role == "end":
                    start = slur_starts.get(slur_id)
                    if start is None:
                        raise RuntimeError(
                            f"Slur {slur_id} has no start endpoint"
                        )
                    expected_slurs.add(
                        (start[0], start[1], number, onset)
                    )

    actual_slurs = set()
    for slur in root.findall(".//SpannerMap/Slur"):
        start = chord_info.get(slur.findtext("startElement") or "")
        end = chord_info.get(slur.findtext("endElement") or "")
        if start is None or end is None:
            raise RuntimeError(
                f"Slur {slur.findtext('eid')} has dangling endpoints"
            )
        actual_slurs.add(
            (start[0], str(start[1]), end[0], str(end[1]))
        )

    errors = []
    if actual_ties != expected_ties:
        errors.append(
            f"ties {sorted(actual_ties)} != {sorted(expected_ties)}"
        )
    if actual_slurs != expected_slurs:
        errors.append(
            f"slurs {sorted(actual_slurs)} != {sorted(expected_slurs)}"
        )
    if errors:
        raise RuntimeError(
            "Curve structure validation failed:\n" + "\n".join(errors)
        )


def validate_db(
    db_path: Path,
    payload: dict,
    pdf_path: Path | None,
    expected_style_sha256: str | None = None,
) -> None:
    if not db_path.is_file():
        raise RuntimeError(f"DB file was not created: {db_path}")
    with zipfile.ZipFile(db_path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Corrupt archive entry: {bad}")
        if expected_style_sha256 is not None:
            style_data = archive.read("score_style.mss")
            actual_style_sha256 = hashlib.sha256(style_data).hexdigest()
            if actual_style_sha256 != expected_style_sha256:
                raise RuntimeError(
                    "DB Score did not preserve the requested layout style"
                )
        mscx_name = next(
            name for name in archive.namelist() if name.endswith(".mscx")
        )
        with tempfile.NamedTemporaryFile(suffix=".mscx", delete=False) as handle:
            handle.write(archive.read(mscx_name))
            temp_path = Path(handle.name)
    try:
        expected = expected_measure_lengths(payload)
        validate_mscx_child_order(temp_path)
        validate_no_unwanted_drum_articulations(temp_path)
        errors = validate_duration_map(temp_path, expected)
        validate_event_timeline(temp_path, payload)
        validate_score_structure(temp_path, payload)
        validate_grace_structure(temp_path, payload)
        validate_rest_structure(temp_path, payload)
        validate_repeat_structure(temp_path, payload)
        validate_curve_structure(temp_path, payload)
    finally:
        temp_path.unlink(missing_ok=True)
    if errors:
        raise RuntimeError(
            "Measure duration validation failed:\n" + "\n".join(errors)
        )
    if pdf_path is not None and (
        not pdf_path.is_file() or pdf_path.stat().st_size == 0
    ):
        raise RuntimeError("Preview PDF was not created")
