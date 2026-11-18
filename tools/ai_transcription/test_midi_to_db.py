#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

import midi_to_db


def varlen(value: int) -> bytes:
    buffer = value & 0x7F
    value >>= 7
    while value:
        buffer <<= 8
        buffer |= (value & 0x7F) | 0x80
        value >>= 7
    result = bytearray()
    while True:
        result.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            return bytes(result)


def midi_file(
    hits: list[tuple[int, int, int]],
    *,
    ppq: int = 480,
    denominator: int = 4,
) -> bytes:
    events = bytearray()
    events += b"\x00\xff\x51\x03\x07\xa1\x20"
    events += b"\x00\xff\x58\x04\x04" + bytes([denominator.bit_length() - 1]) + b"\x18\x08"
    previous = 0
    for tick, pitch, velocity in sorted(hits):
        events += varlen(tick - previous)
        events += bytes([0x99, pitch, velocity])
        previous = tick
    events += varlen(1)
    events += b"\xff\x2f\x00"
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big")
    header += (1).to_bytes(2, "big") + ppq.to_bytes(2, "big")
    track = b"MTrk" + len(events).to_bytes(4, "big") + events
    return header + track


class MidiToDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.style = self.root / "style.mss"
        self.style.write_text("<museScore/>", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_midi(self, hits: list[tuple[int, int, int]], **kwargs) -> Path:
        path = self.root / "test.mid"
        path.write_bytes(midi_file(hits, **kwargs))
        return path

    def test_exact_tick_and_pitch_round_trip(self) -> None:
        hits = [
            (0, 36, 110),
            (0, 38, 100),
            (0, 42, 90),
            (240, 42, 80),
            (480, 36, 100),
            (480, 42, 85),
            (720, 42, 75),
        ]
        midi = self.write_midi(hits)
        output = self.root / "exact.db"
        report = midi_to_db.convert_midi(
            midi,
            output,
            self.style,
            title="Exact",
        )

        self.assertTrue(report["valid"])
        self.assertTrue(report["exactTimelineMatch"])
        self.assertEqual(report["sourceHits"], len(hits))
        self.assertEqual(report["verifiedHits"], len(hits))
        with zipfile.ZipFile(output) as archive:
            mscx_name = next(name for name in archive.namelist() if name.endswith(".mscx"))
            mscx = self.root / "exact.mscx"
            mscx.write_bytes(archive.read(mscx_name))
        self.assertEqual(
            midi_to_db.mscx_note_ticks(mscx, 480),
            sorted((tick, pitch) for tick, pitch, _ in hits),
        )

    def test_duplicate_note_on_is_rejected_instead_of_silently_merged(self) -> None:
        midi = self.write_midi([(0, 36, 100), (0, 36, 90)])
        with self.assertRaisesRegex(ValueError, "duplicate note-on"):
            midi_to_db.convert_midi(
                midi,
                self.root / "duplicate.db",
                self.style,
            )
        self.assertFalse((self.root / "duplicate.db").exists())

    def test_unknown_drum_pitch_is_rejected(self) -> None:
        midi = self.write_midi([(0, 99, 100)])
        with self.assertRaisesRegex(ValueError, "Unsupported drum pitch"):
            midi_to_db.convert_midi(
                midi,
                self.root / "unknown.db",
                self.style,
            )
        self.assertFalse((self.root / "unknown.db").exists())

    def test_non_quarter_meter_is_rejected_until_supported_exactly(self) -> None:
        midi = self.write_midi([(0, 36, 100)], denominator=8)
        with self.assertRaisesRegex(ValueError, "Unsupported MIDI time signature"):
            midi_to_db.convert_midi(
                midi,
                self.root / "meter.db",
                self.style,
            )
        self.assertFalse((self.root / "meter.db").exists())

    def test_auto_shift_aligns_leading_crash_to_downbeat(self) -> None:
        hits = [
            (240, 38, 100),
            (240, 42, 100),
            (240, 49, 100),
            (480, 36, 100),
        ]
        midi = self.write_midi(hits)
        output = self.root / "aligned.db"
        report = midi_to_db.convert_midi(
            midi,
            output,
            self.style,
            start_shift="auto",
        )
        self.assertEqual(report["startShiftTicks"], -240)
        with zipfile.ZipFile(output) as archive:
            mscx_name = next(name for name in archive.namelist() if name.endswith(".mscx"))
            mscx = self.root / "aligned.mscx"
            mscx.write_bytes(archive.read(mscx_name))
        self.assertEqual(
            midi_to_db.mscx_note_ticks(mscx, 480),
            [(0, 38), (0, 42), (0, 49), (240, 36)],
        )

    def test_leading_measure_keeps_generated_groove_in_measure_two(self) -> None:
        hits = [(240, 38, 100), (240, 49, 100)]
        midi = self.write_midi(hits)
        output = self.root / "leading.db"
        report = midi_to_db.convert_midi(
            midi,
            output,
            self.style,
            start_shift="-1/8",
            leading_measures=1,
        )
        self.assertEqual(report["totalTimelineOffsetTicks"], 1680)
        with zipfile.ZipFile(output) as archive:
            mscx_name = next(name for name in archive.namelist() if name.endswith(".mscx"))
            mscx = self.root / "leading.mscx"
            mscx.write_bytes(archive.read(mscx_name))
        self.assertEqual(
            midi_to_db.mscx_note_ticks(mscx, 480),
            [(1920, 38), (1920, 49)],
        )


if __name__ == "__main__":
    unittest.main()
