#!/usr/bin/env python3
"""Regression tests for the DB绘谱 MIDI converter."""

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


def varlen(value):
    value = int(value)
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def meta_event(kind, data):
    return b"\xff" + bytes([kind]) + varlen(len(data)) + data


def track_chunk(events):
    payload = b"".join(varlen(delta) + data for delta, data in events)
    payload += varlen(0) + meta_event(0x2F, b"")
    return b"MTrk" + struct.pack(">I", len(payload)) + payload


def make_midi(path, notes, *, ppq=480, timesig=(4, 4), tempo_us=500000):
    denominator_exponent = timesig[1].bit_length() - 1
    events = [
        (0, meta_event(0x51, tempo_us.to_bytes(3, "big"))),
        (0, meta_event(0x58, bytes([timesig[0], denominator_exponent, 24, 8]))),
    ]
    conductor = track_chunk(events)

    # Build the drum track using absolute event times to keep tests readable.
    absolute = [(0, meta_event(0x03, b"drums")), (0, b"\xc9\x00")]
    for tick, pitch, velocity in notes:
        absolute.append((tick, bytes([0x99, pitch, velocity])))
        absolute.append((tick + 10, bytes([0x89, pitch, 0])))
    absolute.sort(key=lambda item: (item[0], item[1][0] != 0x89))

    drum_payload = bytearray()
    previous = 0
    for tick, data in absolute:
        drum_payload += varlen(tick - previous)
        drum_payload += data
        previous = tick
    drum_payload += varlen(0) + meta_event(0x2F, b"")
    drum = b"MTrk" + struct.pack(">I", len(drum_payload)) + bytes(drum_payload)

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 2, ppq)
    Path(path).write_bytes(header + conductor + drum)


def read_varlen(data, pos):
    value = 0
    for _ in range(4):
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos
    raise ValueError("invalid variable-length quantity")


def note_ons(path):
    data = Path(path).read_bytes()
    assert data[:4] == b"MThd"
    track_count = struct.unpack_from(">H", data, 10)[0]
    pos = 14
    result = []
    for _ in range(track_count):
        assert data[pos:pos + 4] == b"MTrk"
        length = struct.unpack_from(">I", data, pos + 4)[0]
        pos += 8
        end = pos + length
        tick = 0
        running = None
        while pos < end:
            delta, pos = read_varlen(data, pos)
            tick += delta
            status = data[pos]
            if status < 0x80:
                status = running
            else:
                pos += 1
                if status < 0xF0:
                    running = status
            if status == 0xFF:
                kind = data[pos]
                pos += 1
                size, pos = read_varlen(data, pos)
                pos += size
            elif status in (0xF0, 0xF7):
                size, pos = read_varlen(data, pos)
                pos += size
            else:
                size = 1 if status & 0xF0 in (0xC0, 0xD0) else 2
                payload = data[pos:pos + size]
                pos += size
                if status & 0xF0 == 0x90 and payload[1] > 0:
                    result.append((tick, status & 0x0F, payload[0], payload[1]))
        assert pos == end
    return result


class MidiConverterTests(unittest.TestCase):
    converter = None

    def run_converter(self, notes, grid="auto", bpm="source", **midi_options):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        source = root / "input.mid"
        output = root / "output.mid"
        report_path = root / "report.json"
        make_midi(source, notes, **midi_options)
        completed = subprocess.run(
            [
                self.converter,
                "normalize",
                "--input",
                str(source),
                "--output",
                str(output),
                "--report",
                str(report_path),
                "--grid",
                grid,
                "--bpm",
                bpm,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return report, note_ons(output)

    def tearDown(self):
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def test_preserves_every_different_drum_attack(self):
        notes = [
            (0, 36, 110),
            (0, 42, 80),
            (118, 42, 81),
            (240, 38, 120),
            (359, 36, 109),
            (480, 42, 82),
            (599, 38, 118),
            (720, 42, 84),
        ]
        report, onsets = self.run_converter(notes)
        self.assertEqual(report["grid"], "1/16")
        self.assertEqual(report["sourceNoteOns"], len(notes))
        self.assertEqual(report["exactDuplicatesRemoved"], 0)
        self.assertEqual(report["outputHits"], len(notes))
        self.assertEqual(len(onsets), len(notes))
        self.assertTrue(report["valid"])
        self.assertTrue(all(tick % report["gridTicks"] == 0 for tick, _, _, _ in onsets))

    def test_exact_duplicate_is_reported_and_collapsed(self):
        notes = [
            (0, 36, 90),
            (0, 36, 112),
            (240, 38, 120),
        ]
        report, onsets = self.run_converter(notes)
        self.assertEqual(report["sourceNoteOns"], 3)
        self.assertEqual(report["exactDuplicatesRemoved"], 1)
        self.assertEqual(report["outputHits"], 2)
        self.assertEqual(len(onsets), 2)
        self.assertEqual([item[3] for item in onsets if item[2] == 36], [112])

    def test_nearby_same_drum_hits_are_not_lost(self):
        notes = [
            (118, 38, 100),
            (122, 38, 105),
            (360, 36, 112),
        ]
        report, onsets = self.run_converter(notes)
        self.assertEqual(report["exactDuplicatesRemoved"], 0)
        self.assertEqual(report["outputHits"], 3)
        self.assertEqual(report["collisionAdjustments"], 1)
        snare_ticks = sorted(tick for tick, _, pitch, _ in onsets if pitch == 38)
        self.assertEqual(len(snare_ticks), 2)
        self.assertGreater(snare_ticks[1], snare_ticks[0])

    def test_triplet_pattern_selects_triplet_grid(self):
        notes = [(tick, 42, 90) for tick in range(0, 1921, 160)]
        report, onsets = self.run_converter(notes)
        self.assertEqual(report["grid"], "1/8 triplet")
        self.assertEqual(report["gridTicks"], 160)
        self.assertEqual(report["outputHits"], len(notes))
        self.assertEqual(len(onsets), len(notes))

    def test_simultaneous_drums_remain_a_chord(self):
        notes = [
            (0, 36, 110),
            (0, 42, 90),
            (240, 38, 120),
            (240, 42, 90),
        ]
        report, onsets = self.run_converter(notes)
        self.assertEqual(report["outputHits"], 4)
        at_zero = sorted(pitch for tick, _, pitch, _ in onsets if tick == 0)
        at_240 = sorted(pitch for tick, _, pitch, _ in onsets if tick == 240)
        self.assertEqual(at_zero, [36, 42])
        self.assertEqual(at_240, [38, 42])

    def test_custom_ppq_uses_the_same_musical_grid(self):
        notes = [
            (0, 36, 100),
            (240, 42, 80),
            (480, 38, 110),
            (720, 42, 80),
        ]
        report, onsets = self.run_converter(notes, ppq=960)
        self.assertEqual(report["grid"], "1/16")
        self.assertEqual(report["gridTicks"], 240)
        self.assertEqual(len(onsets), len(notes))
        self.assertTrue(all(tick % 240 == 0 for tick, _, _, _ in onsets))

    def test_unknown_percussion_pitch_is_reported(self):
        notes = [
            (0, 36, 100),
            (240, 88, 100),
        ]
        report, onsets = self.run_converter(notes)
        self.assertFalse(report["valid"])
        self.assertIn(88, report["unmappedPitches"])
        self.assertEqual(report["outputHits"], 2)
        self.assertEqual(len(onsets), 2)

    def test_auto_tempo_recovers_actual_pulse(self):
        # The source says 120 BPM, but the repeated kick/snare pulse is closer
        # to a sixteenth-note interval of 307 ticks in the source timeline.
        notes = []
        for index in range(12):
            tick = round(index * 307.0)
            notes.append((tick, 36 if index % 2 == 0 else 38, 100))
        report, onsets = self.run_converter(notes, bpm="auto")
        self.assertGreater(report["outputTempoBpm"], 90.0)
        self.assertLess(report["outputTempoBpm"], 97.0)
        self.assertEqual(report["outputHits"], len(notes))
        self.assertEqual(len(onsets), len(notes))

    def test_auto_tempo_with_sixteenth_hi_hats_stays_readable(self):
        notes = []
        for index in range(33):
            tick = round(index * 122.0)
            notes.append((tick, 42, 80))
            if index % 4 == 0:
                notes.append((tick, 36, 110))
            if index % 4 == 2:
                notes.append((tick, 38, 115))
        report, onsets = self.run_converter(notes, bpm="auto")
        self.assertEqual(report["grid"], "1/16")
        self.assertEqual(report["outputHits"], len(notes))
        self.assertEqual(len(onsets), len(notes))
        self.assertTrue(report["valid"])

    def test_clean_eighth_note_pattern_uses_eighth_grid(self):
        notes = []
        for index in range(16):
            tick = index * 240
            notes.append((tick, 36 if index % 2 == 0 else 38, 105))
            notes.append((tick, 42, 80))
        report, onsets = self.run_converter(notes, bpm="source")
        self.assertEqual(report["grid"], "1/8")
        self.assertEqual(report["outputHits"], len(notes))
        self.assertEqual(len(onsets), len(notes))

    def test_valid_db_package_is_checked_and_moved(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        partial = root / "partial.db"
        final = root / "final.db"
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("score.mscx", "<museScore/>")
            archive.writestr("META-INF/container.xml", "<container/>")

        result = subprocess.run(
            [
                self.converter,
                "verify-db",
                "--input",
                str(partial),
                "--move-to",
                str(final),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(partial.exists())
        self.assertTrue(final.exists())
        self.assertIn("score=score.mscx", result.stdout)

    def test_invalid_db_package_is_rejected_and_discarded(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        partial = root / "partial.db"
        partial.write_text("not a zip", encoding="utf-8")

        result = subprocess.run(
            [
                self.converter,
                "verify-db",
                "--input",
                str(partial),
                "--discard-on-failure",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 7)
        self.assertFalse(partial.exists())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_midi_converter.py <midi-converter>")
    MidiConverterTests.converter = str(Path(sys.argv.pop(1)).resolve())
    unittest.main()
