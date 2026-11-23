#!/usr/bin/env python3
"""Convert a normalized MIDI drum track into a deterministic DB绘谱 .db."""

from __future__ import annotations

import argparse
import base64
import json
import os
import struct
import tempfile
import zipfile
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from build_mscx import DRUMS, DURATIONS, build
from layout_policy import LOWER_DRUMS, voice_for_pitch
from score_validation import validate_duration_map, validate_event_timeline


CRASH_PITCHES = {49, 52, 55, 57}


def read_varlen(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    raise ValueError("Invalid MIDI variable-length quantity")


def read_midi(path: Path) -> tuple[int, list[tuple[int, int, int]], dict]:
    data = path.read_bytes()
    if data[:4] != b"MThd" or len(data) < 14:
        raise ValueError("Not a Standard MIDI File")
    _, track_count, division = struct.unpack_from(">HHH", data, 8)
    if division & 0x8000:
        raise ValueError("SMPTE MIDI timing is not supported")

    offset = 14
    hits: list[tuple[int, int, int]] = []
    tempo = 120.0
    signatures: list[tuple[int, int, int]] = []
    for _ in range(track_count):
        if data[offset : offset + 4] != b"MTrk":
            raise ValueError("Invalid MIDI track")
        length = struct.unpack_from(">I", data, offset + 4)[0]
        pos = offset + 8
        end = pos + length
        tick = 0
        running: int | None = None
        while pos < end:
            delta, pos = read_varlen(data, pos)
            tick += delta
            status = data[pos]
            if status < 0x80:
                if running is None:
                    raise ValueError("MIDI running status without a channel event")
                status = running
            else:
                pos += 1
                if status < 0xF0:
                    running = status

            if status == 0xFF:
                kind = data[pos]
                pos += 1
                size, pos = read_varlen(data, pos)
                payload = data[pos : pos + size]
                pos += size
                if kind == 0x51 and size == 3:
                    tempo = 60_000_000.0 / int.from_bytes(payload, "big")
                elif kind == 0x58 and size >= 2:
                    signatures.append(
                        (tick, int(payload[0]), int(2 ** payload[1]))
                    )
                elif kind == 0x2F:
                    break
                continue
            if status in (0xF0, 0xF7):
                size, pos = read_varlen(data, pos)
                pos += size
                continue
            kind = status & 0xF0
            channel = status & 0x0F
            size = 1 if kind in (0xC0, 0xD0) else 2
            payload = data[pos : pos + size]
            pos += size
            if kind == 0x90 and channel == 9 and len(payload) == 2 and payload[1] > 0:
                hits.append((tick, int(payload[0]), int(payload[1])))
        offset = end

    signatures.sort()
    if not signatures:
        signatures = [(0, 4, 4)]
    return division, sorted(hits), {
        "tempo": tempo,
        "time_signatures": signatures,
    }


def duration_for_ticks(ticks: Fraction, ppq: int) -> tuple[str, int] | None:
    quarter = ticks / ppq
    for value, name, dots in DURATIONS:
        if value == quarter:
            return name, dots
    return None


def measure_spans(
    ppq: int,
    signatures: list[tuple[int, int, int]],
    last_tick: int,
) -> list[tuple[int, int, int]]:
    signatures = sorted(signatures)
    spans: list[tuple[int, int, int]] = []
    tick = 0
    index = 0
    while tick <= last_tick:
        while index + 1 < len(signatures) and signatures[index + 1][0] <= tick:
            index += 1
        _, numerator, denominator = signatures[index]
        if denominator != 4:
            raise ValueError(
                f"Unsupported MIDI time signature {numerator}/{denominator}; "
                "this writer currently supports quarter-note meters"
            )
        measure_ticks = Fraction(ppq * 4 * numerator, denominator)
        if measure_ticks.denominator != 1:
            raise ValueError("MIDI measure length is not an integral tick count")
        end = tick + int(measure_ticks)
        spans.append((tick, end, numerator))
        tick = end
    return spans


def first_measure_ticks(
    ppq: int,
    signatures: list[tuple[int, int, int]],
) -> int:
    if not signatures:
        signatures = [(0, 4, 4)]
    _, numerator, denominator = sorted(signatures)[0]
    ticks = Fraction(ppq * 4 * numerator, denominator)
    if ticks.denominator != 1:
        raise ValueError("MIDI measure length is not an integral tick count")
    return int(ticks)


def infer_start_shift_ticks(
    ppq: int,
    signatures: list[tuple[int, int, int]],
    hits: list[tuple[int, int, int]],
) -> int:
    """Put a leading crash on the downbeat when it is only slightly late.

    Audio-to-MIDI exports often retain a one-sixteenth or one-eighth pickup
    before the first crash.  A crash on beat 2/3/4 is intentional and is not
    moved.  The result is always reported and can be overridden explicitly.
    """
    crashes = sorted(tick for tick, pitch, _ in hits if pitch in CRASH_PITCHES)
    if not crashes:
        return 0
    bar_ticks = first_measure_ticks(ppq, signatures)
    offset = crashes[0] % bar_ticks
    maximum_auto_shift = ppq // 2
    if offset <= 0 or offset > maximum_auto_shift:
        return 0
    grid = max(1, ppq // 4)
    return -int(round(Fraction(offset, grid))) * grid


def resolve_start_shift_ticks(
    value: str,
    ppq: int,
    signatures: list[tuple[int, int, int]],
    hits: list[tuple[int, int, int]],
) -> int:
    if value == "auto":
        return infer_start_shift_ticks(ppq, signatures, hits)
    if value == "none":
        return 0
    aliases = {
        "left-1/16": -ppq // 4,
        "left-1/8": -ppq // 2,
        "left-1/4": -ppq,
        "right-1/16": ppq // 4,
        "right-1/8": ppq // 2,
        "right-1/4": ppq,
        "-1/16": -ppq // 4,
        "-1/8": -ppq // 2,
        "-1/4": -ppq,
        "+1/16": ppq // 4,
        "+1/8": ppq // 2,
        "+1/4": ppq,
    }
    if value not in aliases:
        raise ValueError(
            "Unsupported MIDI start shift; use auto, none, left-1/16, "
            "left-1/8, left-1/4, right-1/16, right-1/8, or right-1/4"
        )
    return aliases[value]


def build_payload(
    title: str,
    tempo: float,
    ppq: int,
    signatures: list[tuple[int, int, int]],
    hits: list[tuple[int, int, int]],
) -> dict:
    if not hits:
        raise ValueError("No drum note-on events found on MIDI channel 10")
    event_counts: dict[tuple[int, int], int] = defaultdict(int)
    for tick, pitch, velocity in hits:
        event_counts[(tick, pitch)] += 1
    duplicate_keys = sorted(
        key for key, count in event_counts.items() if count > 1
    )
    if duplicate_keys:
        preview = ", ".join(str(key) for key in duplicate_keys[:10])
        raise ValueError(
            "Normalized MIDI contains duplicate note-on events; refusing to "
            f"discard attacks silently: {preview}"
        )
    deduplicated = {
        (tick, pitch): velocity for tick, pitch, velocity in hits
    }
    for (_, pitch), _ in deduplicated.items():
        if pitch not in DRUMS:
            raise ValueError(f"Unsupported drum pitch {pitch}")

    spans = measure_spans(ppq, signatures, max(tick for tick, _ in deduplicated))
    by_measure: dict[int, dict[int, list[tuple[int, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for (tick, pitch), velocity in deduplicated.items():
        for number, (start, end, _) in enumerate(spans, 1):
            if start <= tick < end:
                by_measure[number][tick].append((pitch, velocity))
                break
        else:
            raise ValueError(f"MIDI tick {tick} is outside all measures")

    measures = []
    for number, (start, end, beats) in enumerate(spans, 1):
        grouped = by_measure.get(number, {})
        onsets = sorted(grouped)
        voice_onsets: dict[int, list[int]] = defaultdict(list)
        for onset in onsets:
            pitches = {pitch for pitch, _ in grouped[onset]}
            has_lower = bool(pitches & LOWER_DRUMS)
            if has_lower:
                voice_onsets[1].append(onset)
            if pitches - LOWER_DRUMS:
                voice_onsets[0].append(onset)

        beam_group_by_onset: dict[tuple[int, int], str | None] = {}
        for voice, voice_ticks in voice_onsets.items():
            beat_ticks = max(1, ppq)
            current_beat = None
            members: list[int] = []
            for onset in voice_ticks:
                beat = onset // beat_ticks
                gap = (
                    voice_ticks[voice_ticks.index(onset) + 1] - onset
                    if voice_ticks.index(onset) + 1 < len(voice_ticks)
                    else end - onset
                )
                if current_beat is not None and (
                    beat != current_beat or gap > ppq // 2
                ):
                    if len(members) >= 2:
                        group = f"midi:{number}:{voice}:{current_beat}"
                        for member in members:
                            beam_group_by_onset[(member, voice)] = group
                    members = []
                current_beat = beat
                members.append(onset)
            if len(members) >= 2:
                group = f"midi:{number}:{voice}:{current_beat}"
                for member in members:
                    beam_group_by_onset[(member, voice)] = group

        events = []
        for onset in onsets:
            items = grouped[onset]
            upper = sorted({p for p, _ in items if voice_for_pitch(p) == 0})
            lower = sorted({p for p, _ in items if voice_for_pitch(p) == 1})
            parts = []
            for voice, pitches, direction in (
                (0, upper, "up"),
                (1, lower, "down"),
            ):
                if not pitches:
                    continue
                next_onset = min(
                    (
                        value
                        for value in voice_onsets[voice]
                        if value > onset
                    ),
                    default=end,
                )
                duration = duration_for_ticks(
                    Fraction(next_onset - onset, ppq),
                    ppq,
                )
                parts.append(
                    {
                        "voice": direction,
                        "pitches": pitches,
                        "duration": duration[0] if duration else None,
                        "dots": duration[1] if duration else 0,
                        "beams": (
                            int(
                                abs(
                                    Fraction(next_onset - onset, ppq)
                                    / Fraction(1, 4)
                                )
                            )
                            if next_onset - onset <= ppq // 2
                            else 0
                        ),
                        "beam_group": beam_group_by_onset.get((onset, voice)),
                    }
                )
            events.append(
                {
                    "time": str(Fraction(onset - start, ppq * 4)),
                    "x": float(onset - start),
                    "rhythm_x": float(onset - start),
                    "pitches": sorted(upper + lower),
                    "parts": parts,
                    "articulations": [],
                    "review": False,
                    "time_verified": True,
                    "source": "normalized-midi",
                }
            )
        measures.append(
            {
                "number": number,
                "length": beats,
                "system_start": number == 1,
                "start_repeat": False,
                "end_repeat": False,
                "volta": None,
                "events": events,
                "slots": [],
            }
        )
    return {
        "title": title,
        "tempo": round(tempo, 3),
        "measure_count": len(measures),
        "unknown_heads": [],
        "measures": measures,
    }


def build_db_container(
    output: Path,
    mscx_path: Path,
    style_path: Path,
    thumbnail: bytes,
) -> None:
    title = mscx_path.stem
    container = f"""<?xml version="1.0" encoding="UTF-8"?>
<container>
  <rootfiles>
    <rootfile full-path="score_style.mss"/>
    <rootfile full-path="{title}.mscx"/>
    <rootfile full-path="Thumbnails/thumbnail.png"/>
    <rootfile full-path="automation.json"/>
    <rootfile full-path="audiosettings.json"/>
    <rootfile full-path="viewsettings.json"/>
  </rootfiles>
</container>
"""
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("score_style.mss", style_path.read_bytes())
        archive.writestr(f"{title}.mscx", mscx_path.read_bytes())
        archive.writestr("Thumbnails/thumbnail.png", thumbnail)
        archive.writestr("automation.json", "[]")
        archive.writestr(
            "audiosettings.json",
            json.dumps(
                {
                    "activeSoundProfile": "DBScore Basic",
                    "aux": [],
                    "master": {"balance": 0, "fxChain": {}, "volumeDb": 0},
                    "tracks": [],
                },
                indent=4,
            ),
        )
        archive.writestr(
            "viewsettings.json",
            json.dumps({"notation": {"viewMode": "page"}}, indent=4),
        )
        archive.writestr("META-INF/container.xml", container)


def style_and_thumbnail(
    style_source: Path,
    thumbnail_source: Path | None,
) -> tuple[bytes, bytes]:
    """Read a layout style and thumbnail from a .db or use the bundled style."""
    if style_source.suffix.lower() == ".db":
        with zipfile.ZipFile(style_source) as archive:
            style_data = archive.read("score_style.mss")
    else:
        style_data = style_source.read_bytes()
    thumbnail = b""
    source = thumbnail_source or style_source
    if source.suffix.lower() == ".db":
        with zipfile.ZipFile(source) as archive:
            if "Thumbnails/thumbnail.png" in archive.namelist():
                thumbnail = archive.read("Thumbnails/thumbnail.png")
    if not thumbnail:
        # A valid transparent 1x1 PNG keeps the package structurally complete
        # when the converter is run outside the app bundle.
        thumbnail = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGNgYGD4DwABBAEAHnOcQAAAAABJRU5ErkJggg=="
        )
    return style_data, thumbnail


def convert_midi(
    midi_path: Path,
    output: Path,
    style_source: Path,
    *,
    title: str | None = None,
    thumbnail_source: Path | None = None,
    report_path: Path | None = None,
    start_shift: str = "none",
    leading_measures: int = 0,
) -> dict:
    """Convert normalized MIDI to .db and gate on an exact event timeline."""
    ppq, hits, meta = read_midi(midi_path)
    if leading_measures < 0:
        raise ValueError("Leading measures cannot be negative")
    shift_ticks = resolve_start_shift_ticks(
        start_shift,
        ppq,
        meta["time_signatures"],
        hits,
    )
    offset = shift_ticks + leading_measures * first_measure_ticks(
        ppq,
        meta["time_signatures"],
    )
    if hits and min(tick for tick, _, _ in hits) + offset < 0:
        raise ValueError(
            f"Start shift {offset} ticks would place notes before the score"
        )
    if offset:
        hits = [(tick + offset, pitch, velocity) for tick, pitch, velocity in hits]
    payload = build_payload(
        title or midi_path.stem,
        meta["tempo"],
        ppq,
        meta["time_signatures"],
        hits,
    )
    style_data, thumbnail = style_and_thumbnail(style_source, thumbnail_source)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(
        f".{output.name}.ai-transcription-{os.getpid()}.tmp.db"
    )
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            mscx = Path(temp_dir) / f"{output.stem}.mscx"
            style_path = Path(temp_dir) / "score_style.mss"
            style_path.write_bytes(style_data)
            build(payload, mscx)
            validate_duration_map(
                mscx,
                {int(m["number"]): int(m["length"]) for m in payload["measures"]},
            )
            validate_event_timeline(mscx, payload)
            expected_hits = sorted(
                (tick, pitch)
                for tick, pitch, _ in hits
            )
            actual_hits = mscx_note_ticks(mscx, ppq)
            if actual_hits != expected_hits:
                missing = sorted(set(expected_hits) - set(actual_hits))[:20]
                extra = sorted(set(actual_hits) - set(expected_hits))[:20]
                raise ValueError(
                    "Generated score does not match the normalized MIDI timeline: "
                    f"missing={missing}, extra={extra}"
                )
            build_db_container(
                temporary_output,
                mscx,
                style_path,
                thumbnail,
            )
        with zipfile.ZipFile(temporary_output) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"Generated DB archive is corrupt at {bad}")
        os.replace(temporary_output, output)
    finally:
        temporary_output.unlink(missing_ok=True)

    report = {
        "valid": True,
        "source": "normalized-midi",
        "input": str(midi_path),
        "output": str(output),
        "ppq": ppq,
        "sourceHits": len(hits),
        "verifiedHits": len(actual_hits),
        "deduplicatedHits": sum(
            len(event["pitches"])
            for measure in payload["measures"]
            for event in measure["events"]
        ),
        "exactTimelineMatch": actual_hits == expected_hits,
        "unmappedPitches": [],
        "measures": len(payload["measures"]),
        "tempo": payload["tempo"],
        "timeSignatures": meta["time_signatures"],
        "startShiftTicks": shift_ticks,
        "leadingMeasures": leading_measures,
        "totalTimelineOffsetTicks": offset,
        "timingAlignment": start_shift,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def mscx_note_ticks(path: Path, target_ppq: int) -> list[tuple[int, int]]:
    root = ET.parse(path).getroot()
    staff = root.find(".//Score/Staff")
    if staff is None:
        raise ValueError("Generated score has no staff")
    values = {
        "whole": 3840,
        "half": 1920,
        "quarter": 960,
        "eighth": 480,
        "16th": 240,
        "32nd": 120,
        "64th": 60,
    }
    result: list[tuple[int, int]] = []
    measure_start = Fraction(0)
    beats = 4
    for measure in staff.findall("Measure"):
        time_signature = measure.find("./voice/TimeSig")
        if time_signature is not None:
            beats = int(time_signature.findtext("sigN") or beats)
        for voice in measure.findall("voice"):
            cursor = Fraction(0)
            ratio = Fraction(1)
            stack: list[Fraction] = []
            for element in list(voice):
                if element.tag == "Tuplet":
                    stack.append(ratio)
                    ratio *= Fraction(
                        int(element.findtext("normalNotes")),
                        int(element.findtext("actualNotes")),
                    )
                    continue
                if element.tag == "endTuplet":
                    ratio = stack.pop() if stack else Fraction(1)
                    continue
                if element.tag not in {"Chord", "Rest"}:
                    continue
                duration = Fraction(
                    values.get(element.findtext("durationType") or "quarter", 960)
                )
                dots = int(element.findtext("dots") or 0)
                if dots:
                    duration *= sum(
                        Fraction(1, 2**index) for index in range(dots + 1)
                    )
                duration *= ratio
                if element.tag == "Chord":
                    tick = int(
                        (measure_start + cursor)
                        * target_ppq
                        / 960
                    )
                    result.extend(
                        (tick, int(note.findtext("pitch")))
                        for note in element.findall("Note")
                        if note.findtext("pitch") is not None
                    )
                cursor += duration
        measure_start += beats * 960
    return sorted(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("midi", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title")
    parser.add_argument("--style", type=Path, required=True)
    parser.add_argument("--thumbnail-db", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--start-shift",
        default="auto",
        choices=(
            "auto",
            "none",
            "left-1/16",
            "left-1/8",
            "left-1/4",
            "right-1/16",
            "right-1/8",
            "right-1/4",
            "-1/16",
            "-1/8",
            "-1/4",
            "+1/16",
            "+1/8",
            "+1/4",
        ),
    )
    parser.add_argument("--leading-measures", type=int, default=0)
    args = parser.parse_args()

    report = convert_midi(
        args.midi,
        args.output,
        args.style,
        title=args.title,
        thumbnail_source=args.thumbnail_db,
        report_path=args.report,
        start_shift=args.start_shift,
        leading_measures=args.leading_measures,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
