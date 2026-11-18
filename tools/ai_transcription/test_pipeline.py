#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import tempfile
import unittest
import zipfile
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

import build_mscx
import build_visual_proof
import measure_contract
import mxl_extract
import omr_extract
import run_pipeline
import score_validation


class ImageToDbPipelineTests(unittest.TestCase):
    def test_pipeline_reuses_the_single_score_validator_implementation(
        self,
    ) -> None:
        self.assertIs(
            run_pipeline.expected_measure_lengths,
            score_validation.expected_measure_lengths,
        )
        self.assertIs(
            run_pipeline.validate_duration_map,
            score_validation.validate_duration_map,
        )
        self.assertIs(
            run_pipeline.validate_event_timeline,
            score_validation.validate_event_timeline,
        )
        self.assertIs(
            run_pipeline.validate_score_structure,
            score_validation.validate_score_structure,
        )

    def test_rhythm_code_has_no_song_or_measure_specific_branches(self) -> None:
        root = Path(__file__).resolve().parent
        forbidden = re.compile(
            r"\b(?:title|measure\.number)\s*==\s*(?:[\"']|[0-9])"
        )
        offenders = []
        for filename in ("omr_extract.py", "run_pipeline.py", "build_mscx.py"):
            for number, line in enumerate(
                (root / filename).read_text(encoding="utf-8").splitlines(),
                1,
            ):
                if not line.lstrip().startswith("#") and forbidden.search(line):
                    offenders.append(f"{filename}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_standard_contract_files_are_complete_and_unique(self) -> None:
        root = Path(__file__).resolve().parent / "standard_contracts"
        contracts = sorted(root.glob("*.json"))
        self.assertGreaterEqual(len(contracts), 3)
        for path in contracts:
            contract = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(contract["schemaVersion"], 1)
            self.assertEqual(len(contract["measures"]), contract["measureCount"])
            digests = [measure["digest"] for measure in contract["measures"]]
            self.assertEqual(len(digests), len(set(digests)))

    def test_measure_contract_detects_one_note_timing_change(self) -> None:
        payload = {
            "title": "Synthetic",
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [36, 42],
                            "parts": [
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beams": 0,
                                },
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beams": 1,
                                    "beam_group": "source-id-a",
                                },
                            ],
                        },
                        {
                            "time": "1/8",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beams": 1,
                                    "beam_group": "source-id-a",
                                }
                            ],
                        },
                    ],
                    "rests": [],
                }
            ],
        }
        contract = measure_contract.build_contract(payload)
        # Beam IDs are implementation details and must not affect the lock.
        payload["measures"][0]["events"][0]["parts"][1]["beam_group"] = "new-id"
        payload["measures"][0]["events"][1]["parts"][0]["beam_group"] = "new-id"
        self.assertEqual(
            measure_contract.compare_contract(payload, contract),
            [],
        )
        payload["measures"][0]["events"][1]["time"] = "3/16"
        self.assertEqual(
            measure_contract.compare_contract(payload, contract),
            ["measure 1: contract digest changed"],
        )

    def test_measure_contract_locks_rest_voice_and_dots(self) -> None:
        payload = {
            "title": "Synthetic",
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [],
                    "rests": [
                        {
                            "time": "1/4",
                            "voice": "down",
                            "duration": "eighth",
                            "dots": 1,
                        }
                    ],
                }
            ],
        }
        contract = measure_contract.build_contract(payload)
        payload["measures"][0]["rests"][0]["voice"] = "up"
        self.assertEqual(
            measure_contract.compare_contract(payload, contract),
            ["measure 1: contract digest changed"],
        )

    def test_duration_tokenizer_rejects_unmarked_tuplet_values(self) -> None:
        self.assertEqual(
            build_mscx.tokenize(1440),
            [(Fraction(3, 2), "quarter", 1)],
        )
        with self.assertRaisesRegex(ValueError, "explicit tuplet"):
            build_mscx.tokenize(160)

    def test_pitches_are_split_into_two_voices(self) -> None:
        measure = {
            "number": 1,
            "length": 4,
            "events": [{"time": "0", "pitches": [36, 42, 49]}],
        }
        voices = build_mscx.voice_events(measure)
        self.assertEqual(voices[0], {0: [42, 49]})
        self.assertEqual(voices[1], {0: [36]})

    def test_sextuplet_and_accents_survive_native_score_build(self) -> None:
        times = ["0", "1/24", "1/12", "1/8", "1/6", "5/24"]
        payload = {
            "title": "Synthetic",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": time,
                            "pitches": [42],
                            "articulations": ["accent"] if index == 0 else [],
                        }
                        for index, time in enumerate(times)
                    ]
                    + [
                        {
                            "time": "1/4",
                            "pitches": [36, 38],
                            "articulations": [],
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "synthetic.mscx"
            build_mscx.build(payload, output)
            run_pipeline.validate_event_timeline(output, payload)
            root = ET.parse(output).getroot()
            tuplet = root.find(".//Staff/Measure/voice/Tuplet")
            self.assertIsNotNone(tuplet)
            self.assertEqual(tuplet.findtext("actualNotes"), "6")
            self.assertEqual(tuplet.findtext("normalNotes"), "4")
            self.assertEqual(
                root.findtext(".//Chord/Articulation/subtype"),
                "articAccentAbove",
            )

    def test_tie_and_slur_spanners_survive_native_score_build(self) -> None:
        payload = {
            "title": "Curves",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [38],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [38],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beams": 0,
                                }
                            ],
                            "slurs": [{"role": "start", "id": "slur-1"}],
                        },
                        {
                            "time": "1/4",
                            "pitches": [43],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [43],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beams": 0,
                                }
                            ],
                            "slurs": [{"role": "end", "id": "slur-1"}],
                        },
                        {
                            "time": "3/4",
                            "pitches": [49],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [49],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beams": 0,
                                }
                            ],
                            "ties": [
                                {
                                    "role": "start",
                                    "id": "tie-1",
                                    "pitch": 49,
                                }
                            ],
                        },
                    ],
                },
                {
                    "number": 2,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [49],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [49],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beams": 0,
                                }
                            ],
                            "ties": [
                                {
                                    "role": "end",
                                    "id": "tie-1",
                                    "pitch": 49,
                                }
                            ],
                        }
                    ],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "curves.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            self.assertEqual(len(root.findall(".//Note/Tie")), 1)
            self.assertEqual(len(root.findall(".//SpannerMap/Slur")), 1)
            for tie in root.findall(".//Note/Tie"):
                self.assertIsNotNone(tie.findtext("startElement"))
                self.assertIsNotNone(tie.findtext("endElement"))
                self.assertIsNotNone(tie.findtext("eid"))
            for slur in root.findall(".//SpannerMap/Slur"):
                self.assertIsNotNone(slur.findtext("startElement"))
                self.assertIsNotNone(slur.findtext("endElement"))
                self.assertIsNotNone(slur.findtext("eid"))
            score_validation.validate_curve_structure(output, payload)

    def test_tie_flag_between_different_drums_becomes_a_slur(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <slur id="curve-1" tie="true" ctx-grade="0.9"/>
              <relation source="curve-1" target="head-a">
                <slur-head side="LEFT" grade="1"/>
              </relation>
              <relation source="curve-1" target="head-b">
                <slur-head side="RIGHT" grade="1"/>
              </relation>
            </system>
            """
        )
        left = omr_extract.Head(
            source_id="head-a",
            x=10,
            y=10,
            pitch_position=-1,
            shape="NOTEHEAD_CROSS",
            drum=46,
        )
        right = omr_extract.Head(
            source_id="head-b",
            x=20,
            y=10,
            pitch_position=-5,
            shape="NOTEHEAD_CROSS",
            drum=42,
        )
        stats = omr_extract.annotate_head_curves(
            [system],
            [[left, right]],
        )
        self.assertEqual(stats, {"ties": 0, "slurs": 1, "unresolved": 0})
        self.assertIsNone(left.tie_start)
        self.assertEqual(left.slur_starts, ["curve-1"])
        self.assertEqual(right.slur_ends, ["curve-1"])

    def test_same_drum_curve_is_a_tie(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <slur id="tie-1" tie="true" ctx-grade="0.9"/>
              <relation source="tie-1" target="head-a">
                <slur-head side="LEFT" grade="1"/>
              </relation>
              <relation source="tie-1" target="head-b">
                <slur-head side="RIGHT" grade="1"/>
              </relation>
            </system>
            """
        )
        left = omr_extract.Head(
            source_id="head-a",
            x=10,
            y=10,
            pitch_position=3,
            shape="NOTEHEAD_BLACK",
            drum=42,
        )
        right = omr_extract.Head(
            source_id="head-b",
            x=20,
            y=10,
            pitch_position=3,
            shape="NOTEHEAD_BLACK",
            drum=42,
        )
        stats = omr_extract.annotate_head_curves(
            [system],
            [[left, right]],
        )
        self.assertEqual(stats, {"ties": 1, "slurs": 0, "unresolved": 0})
        self.assertEqual(left.tie_start, "tie-1")
        self.assertEqual(right.tie_end, "tie-1")

    def test_curve_on_bass_drum_is_not_a_tie_or_slur(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <slur id="false-kick-curve" tie="true" ctx-grade="0.9"/>
              <relation source="false-kick-curve" target="head-a">
                <slur-head side="LEFT" grade="1"/>
              </relation>
              <relation source="false-kick-curve" target="head-b">
                <slur-head side="RIGHT" grade="1"/>
              </relation>
            </system>
            """
        )
        left = omr_extract.Head(
            source_id="head-a",
            x=10,
            y=10,
            pitch_position=3,
            shape="NOTEHEAD_BLACK",
            drum=36,
        )
        right = omr_extract.Head(
            source_id="head-b",
            x=20,
            y=10,
            pitch_position=3,
            shape="NOTEHEAD_BLACK",
            drum=36,
        )
        stats = omr_extract.annotate_head_curves(
            [system],
            [[left, right]],
        )
        self.assertEqual(stats, {"ties": 0, "slurs": 0, "unresolved": 0})
        self.assertIsNone(left.tie_start)
        self.assertEqual(left.slur_starts, [])
        self.assertEqual(right.slur_ends, [])

    def test_single_lower_voice_stays_single_and_stem_down(self) -> None:
        payload = {
            "title": "Single voice",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [36],
                            "parts": [
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "single.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            measure = root.find(".//Staff/Measure")
            self.assertEqual(len(measure.findall("voice")), 1)
            self.assertEqual(
                measure.findtext("./voice/Chord/StemDirection"),
                "down",
            )

    def test_three_four_onset_uses_whole_note_tick_scale(self) -> None:
        measure = {
            "number": 1,
            "length": 3,
            "events": [{"time": "1/4", "pitches": [36]}],
        }
        details = build_mscx.voice_event_details(measure)
        self.assertEqual(list(details[0]), [960])
        self.assertEqual(details[0][960]["pitches"], [36])

    def test_three_four_geometry_uses_note_values_not_bar_fractions(self) -> None:
        measure = omr_extract.Measure(
            number=1,
            left=100,
            right=1300,
            slots=[omr_extract.Slot(x=120, time=Fraction(0))],
            omr_duration=Fraction(5, 8),
            system_start=True,
        )
        events = [
            {"time": "1/8", "x": 300.0, "rhythm_x": 300.0},
            {"time": "1/4", "x": 500.0, "rhythm_x": 500.0},
            {"time": "3/8", "x": 700.0, "rhythm_x": 700.0},
            {"time": "1/2", "x": 900.0, "rhythm_x": 900.0},
        ]
        self.assertTrue(
            omr_extract.retime_from_horizontal_grid(measure, events, 3, None)
        )
        times = [Fraction(event["time"]) for event in events]
        self.assertTrue(all((time * 16).denominator == 1 for time in times))
        self.assertTrue(all(time < Fraction(3, 4) for time in times))

    def test_horizontal_retime_uses_notehead_center_not_slanted_stem(self) -> None:
        measure = omr_extract.Measure(
            number=10,
            left=806,
            right=1326,
            slots=[omr_extract.Slot(x=44, time=Fraction(0))],
        )
        xs = [851.25, 911.0, 977.5, 1033.0, 1094.0, 1160.5, 1221.5, 1279.5]
        events = [
            {
                "time": str(Fraction(index, 8)),
                "x": x,
                "rhythm_x": x + 12,
            }
            for index, x in enumerate(xs)
        ]
        self.assertTrue(
            omr_extract.retime_from_horizontal_grid(measure, events, 4, 4)
        )
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [Fraction(index, 8) for index in range(8)],
        )

    def test_system_start_regular_pulse_uses_the_time_zero_origin(
        self,
    ) -> None:
        measure = omr_extract.Measure(
            number=77,
            left=200.0,
            right=805.0,
            slots=[omr_extract.Slot(x=132, time=Fraction(0))],
            system_start=True,
        )
        x_values = [334.5, 396.5, 459.0, 515.17, 575.5, 651.0, 702.5, 762.5]
        events = [
            {
                "time": str(Fraction(index * 2 + 1, 16)),
                "x": x,
                "rhythm_x": x,
                "pitches": [51],
            }
            for index, x in enumerate(x_values)
        ]
        changed, verified = omr_extract.normalize_regular_upper_sequence(
            events,
            measure,
            4,
        )
        self.assertEqual(changed, 8)
        self.assertTrue(verified)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [Fraction(index, 8) for index in range(8)],
        )

    def test_system_start_retime_keeps_sparse_sixteenth_relationships(
        self,
    ) -> None:
        measure = omr_extract.Measure(
            number=105,
            left=198.0,
            right=765.0,
            slots=[
                omr_extract.Slot(x=132, time=Fraction(0)),
                omr_extract.Slot(x=218, time=Fraction(1, 4)),
                omr_extract.Slot(x=278, time=Fraction(3, 8)),
                omr_extract.Slot(x=336, time=Fraction(1, 2)),
                omr_extract.Slot(x=402, time=Fraction(5, 8)),
                omr_extract.Slot(x=460, time=Fraction(3, 4)),
                omr_extract.Slot(x=520, time=Fraction(7, 8)),
            ],
            system_start=True,
        )
        x_values = [330.75, 420.25, 476.5, 535.25, 600.5, 661.5, 718.5]
        events = [
            {
                "time": time,
                "x": x,
                "rhythm_x": x,
            }
            for time, x in zip(
                ("1/16", "5/16", "7/16", "9/16", "11/16", "13/16", "15/16"),
                x_values,
            )
        ]
        self.assertTrue(
            omr_extract.retime_from_horizontal_grid(measure, events, 4, 4)
        )
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [
                Fraction(0),
                Fraction(1, 4),
                Fraction(3, 8),
                Fraction(1, 2),
                Fraction(5, 8),
                Fraction(3, 4),
                Fraction(7, 8),
            ],
        )

    def test_retime_does_not_trust_slots_outside_the_bar(self) -> None:
        measure = omr_extract.Measure(
            number=68,
            left=0.0,
            right=400.0,
            slots=[
                omr_extract.Slot(x=44.0, time=Fraction(0)),
                omr_extract.Slot(x=150.0, time=Fraction(1, 4)),
                omr_extract.Slot(x=350.0, time=Fraction(9, 8)),
            ],
        )
        events = [
            {"time": str(time), "x": x, "rhythm_x": x}
            for time, x in (
                (Fraction(0), 44.0),
                (Fraction(1, 4), 150.0),
                (Fraction(9, 8), 350.0),
            )
        ]
        self.assertTrue(
            omr_extract.retime_from_horizontal_grid(measure, events, 4, 4)
        )
        self.assertTrue(
            all(Fraction(event["time"]) < 1 for event in events)
        )
        self.assertNotIn(Fraction(9, 8), [Fraction(e["time"]) for e in events])

    def test_retime_does_not_trust_sub_32nd_slot_noise(self) -> None:
        measure = omr_extract.Measure(
            number=29,
            left=0.0,
            right=400.0,
            slots=[
                omr_extract.Slot(x=50.0, time=Fraction(0)),
                omr_extract.Slot(x=150.0, time=Fraction(1, 4)),
                omr_extract.Slot(x=250.0, time=Fraction(51, 64)),
            ],
        )
        events = [
            {"time": str(time), "x": x, "rhythm_x": x}
            for time, x in (
                (Fraction(0), 50.0),
                (Fraction(1, 4), 150.0),
                (Fraction(51, 64), 250.0),
            )
        ]
        self.assertTrue(
            omr_extract.retime_from_horizontal_grid(measure, events, 4, 4)
        )
        self.assertTrue(
            all(
                Fraction(event["time"]).denominator <= 16
                for event in events
            )
        )

    def test_same_time_upper_and_lower_events_are_not_duplicate_voice(self) -> None:
        upper = {
            "time": "3/4",
            "x": 1222.25,
            "pitches": [37, 48],
            "parts": [{"voice": "up", "pitches": [37, 48]}],
        }
        lower = {
            "time": "3/4",
            "x": 1279.5,
            "pitches": [36],
            "parts": [{"voice": "down", "pitches": [36]}],
        }
        self.assertEqual(omr_extract.event_voice_directions(upper), {"up"})
        self.assertEqual(omr_extract.event_voice_directions(lower), {"down"})
        self.assertFalse(
            omr_extract.event_voice_directions(upper)
            & omr_extract.event_voice_directions(lower)
        )

    def test_cross_voice_engraving_offset_becomes_next_eighth(self) -> None:
        measure = omr_extract.Measure(number=82, left=851, right=1322)
        events = [
            {
                "time": "3/4",
                "x": 1216.5,
                "pitches": [38, 43],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [38, 43],
                        "duration": "quarter",
                        "dots": 0,
                    }
                ],
            },
            {
                "time": "3/4",
                "x": 1274.5,
                "pitches": [36],
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "quarter",
                        "dots": 0,
                    }
                ],
            },
        ]
        changed = omr_extract.split_cross_voice_coincident_onsets(
            events,
            measure,
            4,
        )
        self.assertEqual(changed, 1)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [Fraction(3, 4), Fraction(7, 8)],
        )
        self.assertEqual(
            [event["parts"][0]["duration"] for event in events],
            ["quarter", "eighth"],
        )

    def test_cross_voice_one_sixteenth_offset_is_separated(self) -> None:
        measure = omr_extract.Measure(number=25, left=198, right=808)
        events = [
            {
                "time": "3/4",
                "x": 679.25,
                "pitches": [38, 42],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [38, 42],
                        "duration": "eighth",
                        "dots": 0,
                    }
                ],
            },
            {
                "time": "3/4",
                "x": 717.5,
                "pitches": [36],
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "eighth",
                        "dots": 0,
                    }
                ],
            },
        ]
        changed = omr_extract.split_cross_voice_coincident_onsets(
            events,
            measure,
            4,
        )
        self.assertEqual(changed, 1)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [Fraction(3, 4), Fraction(13, 16)],
        )

    def test_upper_eighth_pair_gets_one_beam_group_across_instruments(
        self,
    ) -> None:
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [pitch],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [pitch],
                        "duration": "eighth",
                        "dots": 0,
                        "beams": 1,
                        "beam_group": group,
                    }
                ],
            }
            for time, x, pitch, group in (
                ("1/2", 1092.5, 51, None),
                ("5/8", 1175.5, 48, "graphic:7:8"),
            )
        ]
        changed = omr_extract.normalize_upper_eighth_beam_groups(
            events,
            66,
            4,
        )
        self.assertGreaterEqual(changed, 1)
        groups = [event["parts"][0]["beam_group"] for event in events]
        self.assertIsNotNone(groups[0])
        self.assertEqual(groups[0], groups[1])

    def test_single_and_double_grace_notes_survive_musescore_build(self) -> None:
        payload = {
            "title": "Grace test",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [38],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [38],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                            "graces": [
                                {
                                    "pitches": [38],
                                    "kind": "acciaccatura",
                                    "voice": "up",
                                },
                                {
                                    "pitches": [38],
                                    "kind": "acciaccatura",
                                    "voice": "up",
                                },
                            ],
                        }
                    ],
                    "rests": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "grace.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            chords = root.findall(".//Staff/Measure/voice/Chord")
            self.assertEqual(
                [chord.find("acciaccatura") is not None for chord in chords[:2]],
                [True, True],
            )
            self.assertIsNone(chords[2].find("acciaccatura"))
            self.assertEqual(
                score_validation.validate_duration_map(output, {1: 4}),
                [],
            )
            score_validation.validate_grace_structure(output, payload)

    def test_double_grace_noteheads_attach_in_source_order(self) -> None:
        template_path = (
            Path(__file__).parent / "templates" / "small_drum_head.png"
        )
        template = np.array(Image.open(template_path).convert("L"))
        image = np.full((100, 140), 255, dtype=np.uint8)
        image[40:56, 30:47] = template
        image[40:56, 50:67] = template
        main = omr_extract.Head(
            source_id="main",
            x=95,
            y=48,
            pitch_position=-1,
            shape="NOTEHEAD_BLACK",
            drum=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "grace.png"
            Image.fromarray(image).save(source)
            changed = omr_extract.annotate_grace_notes_from_image(
                source,
                [[main]],
                template_path,
            )
        self.assertEqual(changed, 2)
        self.assertEqual(len(main.graces), 2)
        self.assertLess(main.graces[0].x, main.graces[1].x)
        self.assertEqual([grace.drum for grace in main.graces], [38, 38])

    def test_snare_and_cymbal_without_kick_stay_in_one_upper_voice(self) -> None:
        payload = {
            "title": "Upper voice",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [38, 42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [38, 42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": "upper-1",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "upper.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            measure = root.find(".//Staff/Measure")
            self.assertEqual(len(measure.findall("voice")), 1)
            self.assertEqual(
                measure.findtext("./voice/Chord/StemDirection"),
                "up",
            )
            self.assertEqual(
                {
                    int(note.text)
                    for note in measure.findall("./voice/Chord/Note/pitch")
                    if note.text
                },
                {38, 42},
            )

    def test_two_voice_kick_is_forced_down_and_beams_are_explicit(self) -> None:
        payload = {
            "title": "Two voices",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [36, 38, 42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [38, 42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": "beam-1",
                                },
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": None,
                                },
                            ],
                        },
                        {
                            "time": "1/8",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": "beam-1",
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "double.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            measure = root.find(".//Staff/Measure")
            self.assertEqual(len(measure.findall("voice")), 2)
            self.assertIsNotNone(measure.find("./voice/Beam"))
            self.assertEqual(
                measure.findtext("./voice[2]/Chord/StemDirection"),
                "down",
            )
            self.assertEqual(
                measure.findtext("./voice[1]/Chord/StemDirection"),
                "up",
            )
            upper_pitches = {
                int(note.text)
                for note in measure.findall("./voice[1]/Chord[1]/Note/pitch")
                if note.text
            }
            self.assertEqual(upper_pitches, {38, 42})

    def test_beam_ids_are_unique_across_measures_and_voices(self) -> None:
        measures = []
        for number in (1, 2):
            measures.append(
                {
                    "number": number,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [36, 42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": "shared-graphic-id",
                                },
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": "shared-graphic-id",
                                },
                            ],
                        },
                        {
                            "time": "1/8",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": "shared-graphic-id",
                                }
                            ],
                        },
                    ],
                }
            )
        payload = {"title": "Beam IDs", "tempo": 100, "measures": measures}
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "beams.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            beam_ids = [
                beam.findtext("eid")
                for beam in root.findall(".//Staff/Measure/voice/Beam")
            ]
            self.assertEqual(len(beam_ids), 4)
            self.assertEqual(len(set(beam_ids)), len(beam_ids))

    def test_unassigned_subquarter_notes_are_auto_beamed_per_measure(self) -> None:
        measures = []
        for number in (1, 2):
            measures.append(
                {
                    "number": number,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": None,
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                        {
                            "time": "1/8",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": None,
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                    ],
                }
            )
        payload = {"title": "Auto beams", "tempo": 100, "measures": measures}
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "auto-beams.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            beams = root.findall(".//Staff/Measure/voice/Beam")
            self.assertEqual(len(beams), 2)
            beam_ids = [beam.findtext("eid") for beam in beams]
            self.assertEqual(len(set(beam_ids)), 2)

    def test_omr_rest_voice_uses_vertical_position(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <rest pitch="-4.3" shape="EIGHTH_REST" id="upper">
                <bounds x="10" y="100" w="20" h="30"/>
              </rest>
              <rest pitch="3.7" shape="QUARTER_REST" id="lower">
                <bounds x="10" y="180" w="20" h="30"/>
              </rest>
              <augmentation-dot id="dot">
                <bounds x="35" y="115" w="8" h="8"/>
              </augmentation-dot>
              <relation source="dot" target="upper">
                <augmentation dx="0.4" dy="0"/>
              </relation>
            </system>
            """
        )
        rests = omr_extract.parse_rests(system)
        self.assertEqual(
            [(rest.voice, rest.duration_type) for rest in rests],
            [("up", "eighth"), ("down", "quarter")],
        )
        self.assertEqual(rests[0].dots, 1)

    def test_open_hihat_circle_above_hihat_maps_to_pitch_46(self) -> None:
        image = Image.new("L", (220, 240), color=255)
        from PIL import ImageDraw

        draw = ImageDraw.Draw(image)
        draw.ellipse((90, 80, 110, 100), outline=0, width=3)
        head = omr_extract.Head(
            source_id="hihat",
            x=100,
            y=165,
            pitch_position=-5,
            shape="NOTEHEAD_CROSS",
            drum=42,
        )
        changed = omr_extract.annotate_open_hihats_from_circles(
            np.asarray(image),
            [[head]],
        )
        self.assertEqual(changed, 1)
        self.assertEqual(head.drum, 46)

    def test_hollow_and_filled_diamonds_map_to_ride_and_bell(self) -> None:
        image = Image.new("L", (300, 180), color=255)
        from PIL import ImageDraw

        draw = ImageDraw.Draw(image)
        hollow = [(100, 80), (112, 100), (100, 120), (88, 100)]
        filled = [(210, 80), (222, 100), (210, 120), (198, 100)]
        draw.polygon(hollow, outline=0, width=3)
        draw.polygon(filled, fill=0)
        heads = [
            omr_extract.Head(
                source_id="ride",
                x=100,
                y=100,
                pitch_position=-4,
                shape="NOTEHEAD_DIAMOND_FILLED",
                drum=53,
            ),
            omr_extract.Head(
                source_id="bell",
                x=210,
                y=100,
                pitch_position=-4,
                shape="NOTEHEAD_DIAMOND_FILLED",
                drum=53,
            ),
        ]
        omr_extract.annotate_diamond_rides_from_image(
            np.asarray(image),
            [heads],
        )
        self.assertEqual(heads[0].drum, 51)
        self.assertEqual(heads[1].drum, 53)

    def test_ride_diamond_inherits_nearby_chord_stem(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <stem id="stem"><bounds x="113" y="80" w="2" h="40"/></stem>
            </system>
            """
        )
        head = omr_extract.Head(
            source_id="ride",
            x=100,
            y=100,
            pitch_position=-4,
            shape="NOTEHEAD_DIAMOND_FILLED",
            drum=51,
        )
        omr_extract.annotate_head_rhythm(system, [head])
        self.assertEqual(head.stem_x, 114)
        self.assertEqual(head.stem_direction, "up")

    def test_staccato_glyphs_do_not_create_extra_articulations(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <articulation shape="STACCATO"><bounds x="10" y="10" w="3" h="3"/></articulation>
              <articulation shape="STACCATISSIMO"><bounds x="30" y="10" w="4" h="4"/></articulation>
              <articulation shape="ACCENT"><bounds x="50" y="10" w="8" h="4"/></articulation>
            </system>
            """
        )
        articulations = omr_extract.parse_articulations(system)
        self.assertEqual(
            [articulation.kind for articulation in articulations],
            ["accent"],
        )

    def test_unwanted_staccato_articulations_are_not_emitted(self) -> None:
        payload = {
            "title": "No stray articulation",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [42],
                            "articulations": ["staccato", "staccatissimo"],
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "no-staccato.mscx"
            build_mscx.build(payload, output)
            score_validation.validate_no_unwanted_drum_articulations(output)
            root = ET.parse(output).getroot()
            self.assertEqual(root.findall(".//Articulation"), [])

    def test_explicit_upper_and_lower_rests_are_preserved(self) -> None:
        payload = {
            "title": "Rests",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [38, 42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [38, 42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                        {
                            "time": "0",
                            "pitches": [36],
                            "parts": [
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                        {
                            "time": "1/4",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                    ],
                    "rests": [
                        {
                            "time": "1/8",
                            "voice": "up",
                            "duration": "eighth",
                            "dots": 0,
                        },
                        {
                            "time": "1/4",
                            "voice": "down",
                            "duration": "quarter",
                            "dots": 0,
                        },
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "rests.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            voices = root.findall(".//Staff/Measure/voice")
            self.assertEqual(len(voices), 2)
            upper_rests = voices[0].findall("Rest")
            lower_rests = voices[1].findall("Rest")
            self.assertTrue(
                any(rest.findtext("durationType") == "eighth" for rest in upper_rests)
            )
            self.assertTrue(
                any(rest.findtext("durationType") == "quarter" for rest in lower_rests)
            )
            score_validation.validate_rest_structure(output, payload)

    def test_trailing_lower_voice_rests_are_hidden_in_two_voice_bar(self) -> None:
        payload = {
            "title": "Hidden lower rests",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [36, 42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                },
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                },
                            ],
                        },
                        {
                            "time": "1/4",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                    ],
                    "rests": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "hidden-rests.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            lower = root.findall(".//Staff/Measure/voice")[1]
            trailing = lower.findall("Rest")
            self.assertTrue(trailing)
            self.assertTrue(all(rest.findtext("visible") == "0" for rest in trailing))

    def test_reviewed_rest_can_be_explicitly_hidden(self) -> None:
        payload = {
            "title": "Hidden reviewed rest",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                        {
                            "time": "1/2",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "half",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                    ],
                    "rests": [
                        {
                            "time": "1/4",
                            "voice": "up",
                            "duration": "quarter",
                            "dots": 0,
                            "hidden": True,
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "hidden-reviewed-rest.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            hidden = [
                rest
                for rest in root.findall(".//Staff/Measure/voice/Rest")
                if rest.findtext("durationType") == "quarter"
            ]
            self.assertTrue(hidden)
            self.assertEqual(hidden[0].findtext("visible"), "0")
            score_validation.validate_rest_structure(output, payload)

    def test_layout_style_replacement_preserves_archive_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "style.db"
            with zipfile.ZipFile(db_path, "w") as archive:
                archive.writestr("score_style.mss", b"old")
                archive.writestr("score.mscx", b"<museScore/>")
            run_pipeline.replace_db_style(db_path, b"new-style")
            with zipfile.ZipFile(db_path) as archive:
                self.assertEqual(archive.read("score_style.mss"), b"new-style")
                self.assertEqual(archive.read("score.mscx"), b"<museScore/>")

    def test_conversion_style_preserves_source_system_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mss"
            output = Path(temp_dir) / "conversion.mss"
            source.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <museScore version="5.00">
                  <Style>
                    <spacingDensity>1</spacingDensity>
                    <minNoteDistance>0.35</minNoteDistance>
                    <barNoteDistance>1.25</barNoteDistance>
                    <noteBarDistance>1.5</noteBarDistance>
                    <minMeasureWidth>8</minMeasureWidth>
                  </Style>
                </museScore>
                """,
                encoding="utf-8",
            )
            run_pipeline.derive_conversion_style(source, output)
            root = ET.parse(output).getroot()
            for key, expected in run_pipeline.CONVERSION_STYLE_OVERRIDES.items():
                self.assertEqual(root.findtext(f"./Style/{key}"), expected)

    def test_conversion_spatium_adapts_to_page_density(self) -> None:
        sparse = {
            "measures": [
                {"number": number, "page_start": number == 1}
                for number in range(1, 36)
            ]
        }
        dense = {
            "measures": [
                {
                    "number": number,
                    "page_start": number in {1, 41},
                }
                for number in range(1, 81)
            ]
        }
        self.assertEqual(
            run_pipeline.conversion_spatium_for_payload(sparse),
            "1.70",
        )
        self.assertEqual(
            run_pipeline.conversion_spatium_for_payload(dense),
            "1.65",
        )

    def test_roundtrip_trimming_removes_only_empty_false_measures(self) -> None:
        page = {
            "measure_count": 4,
            "measures": [
                {"number": 1, "events": [{"time": "0", "pitches": [36]}]},
                {"number": 2, "events": []},
                {"number": 3, "events": [{"time": "1/2", "pitches": [38]}]},
                {"number": 4, "events": []},
            ],
        }
        removed = run_pipeline.trim_spurious_empty_measures(
            page,
            2,
            "page-1",
        )
        self.assertEqual(removed, 2)
        self.assertEqual(
            [measure["events"] for measure in page["measures"]],
            [
                [{"time": "0", "pitches": [36]}],
                [{"time": "1/2", "pitches": [38]}],
            ],
        )
        self.assertEqual(page["measure_count"], 2)

    def test_volta_numbers_are_global_across_pages(self) -> None:
        pages = [
            {
                "measures": [
                    {
                        "number": 1,
                        "length": 4,
                        "start_repeat": True,
                        "volta": None,
                        "events": [],
                    },
                    {
                        "number": 2,
                        "length": 4,
                        "end_repeat": True,
                        "volta": 1,
                        "events": [],
                    },
                ]
            },
            {
                "measures": [
                    {
                        "number": 1,
                        "length": 4,
                        "start_repeat": False,
                        "volta": 1,
                        "events": [],
                    }
                ]
            },
        ]
        combined = run_pipeline.combine_pages(pages, "Cross-page", 100)
        self.assertEqual(
            [measure["volta"] for measure in combined["measures"]],
            [None, 1, 2],
        )

    def test_dbscore_transient_process_error_is_retried(self) -> None:
        with patch.object(
            run_pipeline,
            "_run_dbscore_without_audio_once",
            side_effect=[
                RuntimeError("DB Score failed (51)"),
                None,
            ],
        ) as run_once, patch.object(run_pipeline.time, "sleep"):
            run_pipeline.run_dbscore_without_audio(
                Path("/dbscore"),
                ["-o", "/tmp/out.pdf", "/tmp/score.mscx"],
                Path("/tmp/out.pdf"),
            )
        self.assertEqual(run_once.call_count, 2)

    def test_visual_proof_builds_side_by_side_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            rendered = root / "rendered.png"
            output = root / "comparison.png"
            Image.new("RGB", (800, 1000), "white").save(source)
            Image.new("RGB", (1000, 1000), "white").save(rendered)
            build_visual_proof.side_by_side(
                source,
                rendered,
                output,
                "Test",
            )
            with Image.open(output) as result:
                self.assertEqual(result.height, 1660)
                self.assertGreater(result.width, 2500)

    def test_omr_chord_onset_uses_stack_not_colliding_element_id(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <stack id="3" left="100" right="500">
                <slot id="1" x-offset="20" time-offset="0"/>
                <slot id="2" x-offset="100" time-offset="1/8"/>
              </stack>
              <head id="head" pitch="-5" shape="NOTEHEAD_CROSS">
                <bounds x="112" y="200" w="10" h="10"/>
              </head>
              <stem id="stem"><bounds x="120" y="170" w="2" h="40"/></stem>
              <part>
                <measure id="3">
                  <voice id="3">
                    <slots>
                      <entry>
                        <key>2</key>
                        <value chord="chord" status="BEGIN"/>
                      </entry>
                    </slots>
                  </voice>
                </measure>
              </part>
              <relation source="head" target="stem">
                <head-stem head-side="RIGHT"/>
              </relation>
              <relation source="chord" target="stem"><chord-stem/></relation>
            </system>
            """
        )
        head = omr_extract.Head(
            source_id="head",
            x=117,
            y=205,
            pitch_position=-5,
            shape="NOTEHEAD_CROSS",
            drum=42,
        )
        omr_extract.annotate_head_rhythm(system, [head])
        self.assertEqual(head.time, Fraction(1, 8))
        self.assertTrue(head.time_verified)

    def test_standalone_flag_shape_controls_drum_note_value(self) -> None:
        head = omr_extract.Head(
            source_id="kick",
            x=100,
            y=200,
            pitch_position=3,
            shape="NOTEHEAD_BLACK",
            drum=36,
            stem_direction="down",
            flag_count=2,
        )
        self.assertEqual(omr_extract.note_duration([head]), "16th")
        head.flag_count = 1
        self.assertEqual(omr_extract.note_duration([head]), "eighth")

    def test_double_dot_chain_and_rest_hook_false_dot(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <head id="kick" pitch="3" shape="NOTEHEAD_BLACK">
                <bounds x="100" y="200" w="15" h="10"/>
              </head>
              <head id="other" pitch="3" shape="NOTEHEAD_BLACK">
                <bounds x="200" y="200" w="15" h="10"/>
              </head>
              <augmentation-dot id="dot1">
                <bounds x="120" y="200" w="8" h="8"/>
              </augmentation-dot>
              <augmentation-dot id="dot2">
                <bounds x="130" y="200" w="8" h="8"/>
              </augmentation-dot>
              <augmentation-dot id="rest-hook">
                <bounds x="225" y="195" w="5" h="11"/>
              </augmentation-dot>
              <relation source="dot1" target="kick">
                <augmentation/>
              </relation>
              <relation source="dot2" target="dot1">
                <double-dot/>
              </relation>
              <relation source="rest-hook" target="other">
                <augmentation/>
              </relation>
            </system>
            """
        )
        counts = omr_extract.augmentation_dot_counts(system)
        self.assertEqual(counts["kick"], 2)
        self.assertEqual(counts["other"], 0)

    def test_drum_only_input_rejects_mixed_clefs(self) -> None:
        root = ET.fromstring(
            """
            <sheet>
              <system>
                <clef kind="PERCUSSION"/>
                <clef kind="TREBLE"/>
              </system>
            </sheet>
            """
        )
        with self.assertRaisesRegex(ValueError, "仅支持架子鼓鼓谱"):
            omr_extract.validate_drum_sheet(root)

    def test_drum_only_input_accepts_percussion_clefs(self) -> None:
        root = ET.fromstring(
            """
            <sheet>
              <system><clef kind="PERCUSSION"/></system>
              <system><clef kind="PERCUSSION"/></system>
            </sheet>
            """
        )
        omr_extract.validate_drum_sheet(root)

    def test_closing_barline_attack_is_clamped_inside_measure(self) -> None:
        events = [{"time": "1", "x": 450.0}]
        changed = omr_extract.clamp_out_of_range_events(events, 4)
        self.assertEqual(changed, 1)
        self.assertEqual(Fraction(events[0]["time"]), Fraction(15, 16))

    def test_rests_are_retimed_from_attacks_when_slots_omit_a_subdivision(
        self,
    ) -> None:
        events = [
            {"time": "0", "x": 100.0, "review": False, "pitches": [36]},
            {"time": "1/8", "x": 200.0, "review": False, "pitches": [36]},
            {"time": "1/4", "x": 300.0, "review": False, "pitches": [36]},
            {"time": "9/16", "x": 500.0, "review": False, "pitches": [36]},
        ]
        rests = [
            {
                "time": "1/4",
                "x": 340.0,
                "voice": "down",
                "duration": "quarter",
                "dots": 0,
                "review": False,
            }
        ]
        changed = omr_extract.retime_rests_from_events(events, rests, 4)
        self.assertEqual(changed, 1)
        self.assertEqual(rests[0]["time"], "5/16")
        self.assertFalse(rests[0]["review"])

    def test_rest_moves_after_sustained_bass_note(self) -> None:
        events = [
            {
                "time": "0",
                "x": 100.0,
                "pitches": [36, 42],
                "review": False,
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "quarter",
                    },
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                    },
                ],
            },
            {
                "time": "5/8",
                "x": 500.0,
                "pitches": [36, 42],
                "review": False,
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "eighth",
                    },
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                    },
                ],
            },
            {
                "time": "3/4",
                "x": 600.0,
                "pitches": [38, 42],
                "review": False,
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [38, 42],
                        "duration": "eighth",
                    }
                ],
            },
        ]
        rests = [
            {
                "time": "21/32",
                "x": 580.0,
                "voice": "down",
                "duration": "quarter",
                "dots": 0,
                "review": False,
            }
        ]
        omr_extract.retime_rests_from_events(events, rests, 4)
        self.assertEqual(rests[0]["time"], "3/4")
        self.assertEqual(rests[0]["review_resolution"], "note-grid-retime")

    def test_graphic_beam_does_not_cross_to_opposite_stem_side(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <line><point x="0" y="50"/><point x="300" y="250"/></line>
            </system>
            """
        )
        heads = [
            omr_extract.Head(
                source_id=f"kick-{index}",
                x=x,
                y=200,
                pitch_position=3,
                shape="NOTEHEAD_BLACK",
                drum=36,
                stem_direction="down",
            )
            for index, x in enumerate((100.0, 180.0))
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "wrong-side-beam.png"
            image = Image.new("L", (300, 300), color=255)
            from PIL import ImageDraw

            draw = ImageDraw.Draw(image)
            draw.rectangle((50, 95, 220, 105), fill=0)
            image.save(image_path)
            omr_extract.annotate_graphic_beams(
                image_path,
                [system],
                [heads],
            )
        self.assertTrue(all(head.beam_group is None for head in heads))

    def test_full_width_staff_line_is_not_recovered_as_a_beam(self) -> None:
        system = ET.fromstring(
            """
            <system>
              <line><point x="0" y="20"/><point x="300" y="260"/></line>
            </system>
            """
        )
        heads = [
            omr_extract.Head(
                source_id=f"head-{index}",
                x=x,
                y=200,
                pitch_position=-5,
                shape="NOTEHEAD_CROSS",
                drum=42,
            )
            for index, x in enumerate((80.0, 180.0))
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "staff-line.png"
            image = Image.new("L", (300, 300), color=255)
            from PIL import ImageDraw

            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 145, 299, 155), fill=0)
            image.save(image_path)
            omr_extract.annotate_graphic_beams(
                image_path,
                [system],
                [heads],
            )
        self.assertTrue(all(head.beam_group is None for head in heads))

    def test_beamed_eighth_member_is_restored_to_expected_grid(self) -> None:
        events = [
            {
                "time": "1/2",
                "x": 100.0,
                "pitches": [42],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                        "dots": 0,
                        "beam_group": "g1",
                    }
                ],
            },
            {
                "time": "35/64",
                "x": 180.0,
                "pitches": [42],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                        "dots": 0,
                        "beam_group": "g1",
                    }
                ],
            },
        ]
        changed = omr_extract.normalize_beamed_group_timing(events)
        self.assertEqual(changed, 1)
        self.assertEqual(events[1]["time"], "5/8")

    def test_mixed_beam_groups_are_rebuilt_after_bar_grid(self) -> None:
        measure = omr_extract.Measure(
            number=68,
            left=1765.0,
            right=2366.0,
        )
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [pitch],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [pitch],
                        "duration": duration,
                        "dots": 0,
                        "beam_group": group,
                    }
                ],
            }
            for time, x, pitch, duration, group in (
                ("1/2", 2095.5, 43, "16th", "g1"),
                ("5/8", 2153.5, 43, "eighth", "g1"),
                ("11/16", 2207.5, 38, "16th", "g1"),
                ("13/16", 2248.5, 38, "eighth", "g2"),
                ("7/8", 2301.5, 43, "16th", "g2"),
                ("15/16", 2341.5, 43, "16th", "g2"),
            )
        ]
        changed = omr_extract.normalize_beamed_group_timing(
            events,
            measure=measure,
            beats=4,
        )
        self.assertEqual(changed, 2)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [
                Fraction(1, 2),
                Fraction(9, 16),
                Fraction(11, 16),
                Fraction(3, 4),
                Fraction(7, 8),
                Fraction(15, 16),
            ],
        )

    def test_last_note_in_beam_group_is_written_as_beam_end(self) -> None:
        payload = {
            "title": "Beam end",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": time,
                            "pitches": [pitch],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [pitch],
                                    "duration": duration,
                                    "dots": 0,
                                    "beams": beams,
                                    "beam_group": "snare-crash",
                                }
                            ],
                        }
                        for time, pitch, duration, beams in (
                            ("3/4", 38, "16th", 2),
                            ("13/16", 49, "eighth", 1),
                        )
                    ],
                    "rests": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "beam-end.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            modes = [
                chord.findtext("BeamMode")
                for chord in root.findall(".//Staff/Measure/voice/Chord")
            ]
            self.assertEqual(modes, ["begin", "end"])

    def test_complete_rest_anchors_following_chord_to_rest_end(self) -> None:
        measure = omr_extract.Measure(
            number=71,
            left=1404.0,
            right=1848.0,
        )
        events = [
            {
                "time": time,
                "x": x,
                "pitches": pitches,
                "parts": [
                    {
                        "voice": "up",
                        "pitches": pitches,
                        "duration": duration,
                        "dots": 0,
                    }
                ],
            }
            for time, x, pitches, duration in (
                ("0", 1449.0, [36, 49], "quarter"),
                ("1/4", 1537.5, [38], "eighth"),
                ("3/8", 1594.0, [36, 49], "eighth"),
                ("11/16", 1781.5, [38, 49], "quarter"),
            )
        ]
        rests = [
            {
                "time": "1/2",
                "x": 1654.0,
                "voice": "up",
                "duration": "quarter",
                "dots": 0,
                "review": False,
            },
            {
                "time": "11/16",
                "x": 1775.5,
                "voice": "down",
                "duration": "quarter",
                "dots": 0,
                "review": False,
            },
        ]
        changed = omr_extract.align_onsets_to_rest_ends(
            events,
            rests,
            measure,
            4,
        )
        self.assertEqual(changed, 1)
        self.assertEqual(events[-1]["time"], "3/4")
        omr_extract.retime_rests_from_events(events, rests, 4)
        self.assertEqual(rests[0]["time"], "1/2")
        self.assertNotIn("render_voice", rests[0])
        self.assertEqual(rests[1]["time"], "3/4")

    def test_half_rest_and_opposite_voice_attack_share_beat_three(self) -> None:
        measure = omr_extract.Measure(
            number=68,
            left=1765.0,
            right=2366.0,
        )
        rests = [
            {
                "time": "5/8",
                "x": 2091.5,
                "voice": "down",
                "duration": "half",
                "dots": 0,
                "review": False,
            }
        ]
        event = {
            "time": "5/8",
            "x": 2095.5,
            "pitches": [43],
            "parts": [
                {
                    "voice": "up",
                    "pitches": [43],
                    "duration": "16th",
                    "dots": 0,
                }
            ],
        }
        self.assertEqual(
            omr_extract.normalize_long_rest_starts(rests, measure, 4),
            1,
        )
        self.assertEqual(rests[0]["time"], "1/2")
        self.assertEqual(
            omr_extract.align_onsets_to_rest_starts(
                [event],
                rests,
                4,
            ),
            1,
        )
        self.assertEqual(event["time"], "1/2")

    def test_beamed_group_does_not_move_confirmed_triplet_onset(self) -> None:
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [53],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [53],
                        "duration": "eighth",
                        "dots": 0,
                        "beam_group": group,
                    }
                ],
            }
            for time, x, group in (
                ("5/24", 100.0, "g1"),
                ("7/24", 180.0, "g1"),
            )
        ]
        changed = omr_extract.normalize_beamed_group_timing(
            events,
            has_tuplet=True,
        )
        self.assertEqual(changed, 0)
        self.assertEqual(events[1]["time"], "7/24")

    def test_adjacent_eighth_beam_groups_share_one_continuous_grid(
        self,
    ) -> None:
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [42],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                        "dots": 0,
                        "beam_group": group,
                    }
                ],
            }
            for time, x, group in (
                ("0", 1386.0, "g1"),
                ("1/8", 1443.0, "g1"),
                ("1/4", 1509.0, "g2"),
                ("3/8", 1560.0, "g2"),
                ("1/2", 1633.0, "g3"),
                ("5/8", 1691.0, "g3"),
                ("21/32", 1757.0, "g4"),
                ("25/32", 1808.0, "g4"),
            )
        ]
        changed = omr_extract.normalize_sequential_beam_groups(events)
        self.assertEqual(changed, 2)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [
                Fraction(index, 8)
                for index in range(8)
            ],
        )
        self.assertEqual(
            events[-2]["review_resolution"],
            "sequential-beam-grid",
        )

    def test_regular_upper_sequence_restores_eighth_pulse(self) -> None:
        measure = omr_extract.Measure(
            number=10,
            left=806,
            right=1326,
            slots=[omr_extract.Slot(x=44, time=Fraction(0))],
        )
        xs = [851.25, 911.0, 977.5, 1033.0, 1094.0, 1160.5, 1221.5, 1279.5]
        events = [
            {
                "time": (
                    "13/16" if index == 6 else str(Fraction(index, 8))
                ),
                "x": x,
                "pitches": [42],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                        "dots": 0,
                        "beams": 1,
                        "beam_group": f"g{index // 2}",
                    }
                ],
                "review": False,
            }
            for index, x in enumerate(xs)
        ]
        changed, verified = omr_extract.normalize_regular_upper_sequence(
            events,
            measure,
            4,
        )
        self.assertEqual(changed, 1)
        self.assertTrue(verified)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [Fraction(index, 8) for index in range(8)],
        )

    def test_regular_upper_sequence_allows_an_eighth_rest_gap(self) -> None:
        measure = omr_extract.Measure(number=113, left=198, right=1515)
        positions = [
            (332.5, [51]),
            (483.5, [51]),
            (635.5, [38, 51]),
            (781.5, [51]),
            (1083.5, [48]),
            (1233.5, [48]),
            (1379.5, [36]),
        ]
        events = [
            {
                "time": old_time,
                "x": x,
                "pitches": pitches,
                "parts": [
                    {
                        "voice": "up",
                        "pitches": pitches,
                        "duration": "quarter" if 51 in pitches else "eighth",
                        "dots": 0,
                        "beams": 0,
                        "beam_group": None,
                    }
                ],
            }
            for (x, pitches), old_time in zip(
                positions,
                ("0", "1/8", "1/4", "3/8", "5/8", "3/4", "7/8"),
            )
        ]
        _, verified = omr_extract.normalize_regular_upper_sequence(
            events,
            measure,
            4,
        )
        self.assertTrue(verified)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [
                Fraction(0),
                Fraction(1, 8),
                Fraction(1, 4),
                Fraction(3, 8),
                Fraction(5, 8),
                Fraction(3, 4),
                Fraction(7, 8),
            ],
        )
        ride_events = [
            event for event in events if 51 in event["pitches"]
        ]
        self.assertEqual(
            [event["parts"][0]["beam_group"] for event in ride_events],
            [f"ride:113:{beat}" for beat in (0, 0, 1, 1)],
        )

    def test_regular_upper_sequence_does_not_flatten_mixed_sixteenths(
        self,
    ) -> None:
        measure = omr_extract.Measure(number=34, left=1629, right=2366)
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [43],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [43],
                        "duration": "16th" if "/16" in time else "eighth",
                        "dots": 0,
                        "beams": 2 if "/16" in time else 1,
                        "beam_group": "existing",
                    }
                ],
            }
            for time, x in (
                ("0", 1676.0),
                ("1/8", 1746.5),
                ("1/4", 1813.5),
                ("3/8", 1918.5),
                ("7/16", 1970.5),
                ("1/2", 2022.5),
                ("9/16", 2073.5),
                ("5/8", 2126.5),
            )
        ]
        before = [event["time"] for event in events]
        changed, verified = omr_extract.normalize_regular_upper_sequence(
            events,
            measure,
            4,
        )
        self.assertEqual(changed, 0)
        self.assertFalse(verified)
        self.assertEqual([event["time"] for event in events], before)

    def test_regular_upper_sequence_accepts_valid_eighths_with_lower_noise(
        self,
    ) -> None:
        measure = omr_extract.Measure(number=29, left=198, right=774)
        events = [
            {
                "time": str(Fraction(index, 8)),
                "x": 330.75 + index * 55,
                "pitches": [42],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                        "dots": 0,
                        "beams": 1,
                        "beam_group": "upper",
                    }
                ],
            }
            for index in range(8)
        ]
        events.append(
            {
                "time": "51/64",
                "x": 688.5,
                "pitches": [36],
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "eighth",
                        "dots": 0,
                    }
                ],
            }
        )
        changed, verified = omr_extract.normalize_regular_upper_sequence(
            events,
            measure,
            4,
        )
        self.assertEqual(changed, 0)
        self.assertTrue(verified)
        self.assertEqual(
            [
                event["time"]
                for event in sorted(events, key=lambda item: item["x"])
            ],
            [
                "0",
                "1/8",
                "1/4",
                "3/8",
                "1/2",
                "5/8",
                "3/4",
                "51/64",
                "7/8",
            ],
        )

    def test_sparse_lower_rest_realigns_same_x_upper_attack(self) -> None:
        events = [
            {
                "time": "3/16",
                "x": 184.5,
                "pitches": [38, 43],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [38, 43],
                        "duration": "eighth",
                        "dots": 0,
                    }
                ],
            },
            {
                "time": "5/16",
                "x": 261.5,
                "pitches": [36],
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "eighth",
                        "dots": 1,
                    }
                ],
            },
            {
                "time": "3/8",
                "x": 289.5,
                "pitches": [43],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [43],
                        "duration": "16th",
                        "dots": 0,
                    }
                ],
            },
        ]
        rests = [
            {
                "time": "1/4",
                "x": 184.25,
                "voice": "down",
                "duration": "16th",
                "dots": 0,
                "source": "sparse-sixteenth-pattern",
            }
        ]
        changed = omr_extract.reconcile_sparse_lower_onset_alignment(
            events,
            rests,
        )
        self.assertEqual(changed, 1)
        self.assertEqual(events[0]["time"], "1/4")
        self.assertEqual(
            events[0]["review_resolution"],
            "sparse-lower-onset-alignment",
        )

    def test_sparse_lower_alignment_requires_matching_geometry(
        self,
    ) -> None:
        events = [
            {
                "time": "3/16",
                "x": 184.5,
                "pitches": [38, 43],
                "parts": [{"voice": "up", "pitches": [38, 43]}],
            }
        ]
        rests = [
            {
                "time": "1/4",
                "x": 220.0,
                "voice": "down",
                "duration": "16th",
                "dots": 0,
                "source": "sparse-sixteenth-pattern",
            }
        ]
        changed = omr_extract.reconcile_sparse_lower_onset_alignment(
            events,
            rests,
        )
        self.assertEqual(changed, 0)
        self.assertEqual(events[0]["time"], "3/16")

    def test_voice_pulse_sequence_skips_omitted_eighth_rest(self) -> None:
        measure = omr_extract.Measure(number=29, left=996, right=1456)
        events = [
            {
                "time": time,
                "x": x,
                "pitches": pitches,
                "parts": [
                    {
                        "voice": voice,
                        "pitches": pitches,
                        "duration": duration,
                        "dots": 0,
                    }
                    for voice, pitches, duration in parts
                ],
            }
            for time, x, pitches, parts in (
                ("0", 1044.0, [36, 42], (("down", [36], "eighth"), ("up", [42], "eighth"))),
                ("1/8", 1107.0, [36, 42], (("down", [36], "eighth"), ("up", [42], "eighth"))),
                ("1/4", 1232.0, [36, 42], (("down", [36], "eighth"), ("up", [42], "eighth"))),
                ("3/8", 1295.0, [36, 42], (("down", [36], "quarter"), ("up", [42], "quarter"))),
                ("5/8", 1387.0, [38, 43], (("up", [38, 43], "quarter"),)),
            )
        ]
        changed = omr_extract.normalize_voice_pulse_sequences(
            events,
            measure,
            4,
        )
        self.assertGreaterEqual(changed, 3)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [
                Fraction(0),
                Fraction(1, 8),
                Fraction(3, 8),
                Fraction(1, 2),
                Fraction(3, 4),
            ],
        )

    def test_voice_pulse_sequence_recovers_offbeat_bass_drum(self) -> None:
        measure = omr_extract.Measure(number=22, left=1326, right=1847)
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [36],
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "eighth",
                        "dots": 0,
                    }
                ],
            }
            for time, x in (
                ("1/8", 1433.5),
                ("5/16", 1555.5),
                ("1/2", 1677.5),
                ("3/4", 1799.5),
            )
        ]
        omr_extract.normalize_voice_pulse_sequences(events, measure, 4)
        self.assertEqual(
            [Fraction(event["time"]) for event in events],
            [Fraction(1, 8), Fraction(3, 8), Fraction(5, 8), Fraction(7, 8)],
        )

    def test_voice_pulse_preserves_slot_confirmed_sixteenth(self) -> None:
        measure = omr_extract.Measure(
            number=16,
            left=1326.0,
            right=1847.0,
            slots=[
                omr_extract.Slot(x=44.0, time=Fraction(0)),
                omr_extract.Slot(x=103.0, time=Fraction(1, 8)),
                omr_extract.Slot(x=165.0, time=Fraction(1, 4)),
                omr_extract.Slot(x=221.0, time=Fraction(3, 8)),
                omr_extract.Slot(x=252.0, time=Fraction(7, 16)),
                omr_extract.Slot(x=296.0, time=Fraction(1, 2)),
                omr_extract.Slot(x=355.0, time=Fraction(5, 8)),
                omr_extract.Slot(x=417.0, time=Fraction(3, 4)),
                omr_extract.Slot(x=473.0, time=Fraction(7, 8)),
            ],
        )
        events = [
            {
                "time": time,
                "x": x,
                "pitches": pitches,
                "parts": [
                    {
                        "voice": "down",
                        "pitches": pitches,
                        "duration": duration,
                        "dots": 0,
                    }
                ],
            }
            for time, x, pitches, duration in (
                ("0", 1370.75, [36], "quarter"),
                ("7/16", 1578.5, [36], "16th"),
                ("5/8", 1681.75, [36], "eighth"),
                ("3/4", 1744.17, [44], "quarter"),
            )
        ]
        before = [event["time"] for event in events]
        self.assertEqual(
            omr_extract.normalize_voice_pulse_sequences(events, measure, 4),
            0,
        )
        self.assertEqual([event["time"] for event in events], before)

    def test_voice_pulse_preserves_slot_confirmed_irregular_gap(self) -> None:
        measure = omr_extract.Measure(
            number=69,
            left=198.0,
            right=805.0,
            slots=[
                omr_extract.Slot(x=132.0, time=Fraction(0)),
                omr_extract.Slot(x=193.0, time=Fraction(1, 8)),
                omr_extract.Slot(x=258.0, time=Fraction(1, 4)),
                omr_extract.Slot(x=314.0, time=Fraction(3, 8)),
                omr_extract.Slot(x=374.0, time=Fraction(1, 2)),
                omr_extract.Slot(x=438.0, time=Fraction(5, 8)),
                omr_extract.Slot(x=502.0, time=Fraction(3, 4)),
                omr_extract.Slot(x=560.0, time=Fraction(13, 16)),
            ],
        )
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [36],
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": "eighth",
                        "dots": 0,
                    }
                ],
            }
            for time, x in (
                ("1/8", 391.75),
                ("3/8", 513.5),
                ("5/8", 636.5),
                ("13/16", 758.5),
            )
        ]
        before = [event["time"] for event in events]
        self.assertEqual(
            omr_extract.normalize_voice_pulse_sequences(events, measure, 4),
            0,
        )
        self.assertEqual([event["time"] for event in events], before)

    def test_voice_pulse_does_not_reconstruct_from_three_attacks(self) -> None:
        measure = omr_extract.Measure(
            number=37,
            left=1531.0,
            right=1898.0,
        )
        events = [
            {
                "time": time,
                "x": x,
                "pitches": pitches,
                "parts": [
                    {
                        "voice": "up",
                        "pitches": pitches,
                        "duration": "quarter",
                        "dots": 0,
                    }
                ],
            }
            for time, x, pitches in (
                ("0", 1575.75, [36, 49]),
                ("3/4", 1807.25, [38, 42]),
                ("7/8", 1856.0, [46]),
            )
        ]
        before = [event["time"] for event in events]
        self.assertEqual(
            omr_extract.normalize_voice_pulse_sequences(events, measure, 4),
            0,
        )
        self.assertEqual([event["time"] for event in events], before)

    def test_voice_pulse_sequence_leaves_irregular_grace_phrase_alone(
        self,
    ) -> None:
        measure = omr_extract.Measure(number=82, left=851, right=1322)
        events = [
            {
                "time": time,
                "x": x,
                "pitches": pitches,
                "parts": [
                    {
                        "voice": "up",
                        "pitches": pitches,
                        "duration": duration,
                        "dots": 0,
                    }
                ],
            }
            for time, x, pitches, duration in (
                ("0", 923.5, [38], "quarter"),
                ("1/4", 1004.5, [36, 49], "quarter"),
                ("5/8", 1154.5, [47], "eighth"),
                ("3/4", 1216.5, [38, 43], "quarter"),
                ("3/4", 1274.5, [36], "quarter"),
            )
        ]
        before = [event["time"] for event in events]
        self.assertEqual(
            omr_extract.normalize_voice_pulse_sequences(events, measure, 4),
            0,
        )
        self.assertEqual([event["time"] for event in events], before)

    def test_isolated_64th_slot_noise_snaps_to_sixteenth_grid(self) -> None:
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [36],
                "parts": [{"voice": "down", "pitches": [36]}],
            }
            for time, x in (
                ("0", 330.75),
                ("11/16", 608.5),
                ("51/64", 688.5),
                ("7/8", 736.0),
            )
        ]
        self.assertEqual(
            omr_extract.snap_isolated_subdivision_noise(events, 4),
            1,
        )
        self.assertEqual(events[-2]["time"], "13/16")
        self.assertEqual(
            events[-2]["review_resolution"],
            "isolated-grid-noise",
        )

    def test_two_subdivision_noise_events_are_not_silently_snapped(
        self,
    ) -> None:
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [36],
                "parts": [{"voice": "down", "pitches": [36]}],
            }
            for time, x in (
                ("51/64", 688.5),
                ("25/32", 700.0),
            )
        ]
        before = [event["time"] for event in events]
        self.assertEqual(
            omr_extract.snap_isolated_subdivision_noise(events, 4),
            0,
        )
        self.assertEqual([event["time"] for event in events], before)

    def test_sparse_lower_sixteenths_use_dotted_eighth_and_final_16th(
        self,
    ) -> None:
        measure = omr_extract.Measure(
            number=33,
            left=891,
            right=1629,
            slots=[
                omr_extract.Slot(x=44.0, time=Fraction(0)),
                omr_extract.Slot(x=117.0, time=Fraction(1, 8)),
                omr_extract.Slot(x=184.0, time=Fraction(1, 4)),
                omr_extract.Slot(x=289.0, time=Fraction(3, 8)),
                omr_extract.Slot(x=390.0, time=Fraction(1, 2)),
                omr_extract.Slot(x=580.0, time=Fraction(3, 4)),
            ],
        )
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [36],
                "parts": [
                    {
                        "voice": "down",
                        "pitches": [36],
                        "duration": duration,
                        "dots": 0,
                        "beams": 0,
                        "beam_group": None,
                    }
                ],
            }
            for time, x, duration in (
                ("0", 935.75, "quarter"),
                ("1/4", 1125.5, "eighth"),
                ("11/16", 1419.5, "16th"),
            )
        ]
        rests = [
            {
                "time": "1/4",
                "x": 1075.0,
                "voice": "down",
                "duration": "16th",
                "dots": 0,
                "shape": "ONE_16TH_REST",
                "pitch_position": 6.7,
                "review": False,
                "source": "audiveris-rest",
            },
            {
                "time": "7/16",
                "x": 1087.0,
                "voice": "down",
                "duration": "eighth",
                "dots": 1,
                "shape": "EIGHTH_REST",
                "pitch_position": 5.6,
                "review": False,
                "source": "audiveris-rest",
            },
        ]
        omr_extract.normalize_sparse_lower_sixteenths(
            events,
            rests,
            measure,
            4,
        )
        self.assertEqual(events[1]["time"], "5/16")
        self.assertEqual(events[1]["parts"][0]["duration"], "eighth")
        self.assertEqual(events[1]["parts"][0]["dots"], 1)
        self.assertEqual(events[2]["time"], "11/16")
        self.assertEqual(events[2]["parts"][0]["duration"], "16th")
        self.assertEqual(
            [
                (
                    Fraction(rest["time"]),
                    rest["duration"],
                    rest["dots"],
                )
                for rest in rests
            ],
            [
                (Fraction(1, 4), "16th", 0),
                (Fraction(1, 2), "eighth", 1),
            ],
        )

    def test_ride_sequence_uses_hihat_rhythm_and_beam_groups(self) -> None:
        measure = omr_extract.Measure(
            number=59,
            left=1337,
            right=1853,
            slots=[omr_extract.Slot(x=45, time=Fraction(0))],
        )
        xs = [1382.5, 1445.5, 1508.5, 1565.0, 1626.5, 1687.5, 1750.5, 1810.5]
        events = []
        for index, x in enumerate(xs):
            pitch = 49 if index == 0 else 51
            events.append(
                {
                    "time": (
                        "3/16"
                        if index == 1
                        else str(Fraction(index, 8))
                    ),
                    "x": x,
                    "pitches": [pitch],
                    "parts": [
                        {
                            "voice": "up",
                            "pitches": [pitch],
                            "duration": "quarter" if pitch == 51 else "quarter",
                            "dots": 0,
                            "beams": 0,
                            "beam_group": None,
                        }
                    ],
                    "review": False,
                }
            )
        _, verified = omr_extract.normalize_regular_upper_sequence(
            events,
            measure,
            4,
        )
        self.assertTrue(verified)
        ride_events = [
            event for event in events
            if 51 in event["pitches"]
        ]
        self.assertEqual(
            [Fraction(event["time"]) for event in ride_events],
            [Fraction(index, 8) for index in range(1, 8)],
        )
        groups = [event["parts"][0]["beam_group"] for event in ride_events]
        self.assertIsNone(groups[0])
        self.assertEqual(groups[1], groups[2])
        self.assertEqual(groups[3], groups[4])
        self.assertEqual(groups[5], groups[6])

    def test_sequential_beam_grid_preserves_a_wide_gap(self) -> None:
        events = [
            {
                "time": time,
                "x": x,
                "pitches": [42],
                "parts": [
                    {
                        "voice": "up",
                        "pitches": [42],
                        "duration": "eighth",
                        "dots": 0,
                        "beam_group": group,
                    }
                ],
            }
            for time, x, group in (
                ("0", 100.0, "g1"),
                ("1/8", 150.0, "g1"),
                ("1/2", 400.0, "g2"),
                ("5/8", 450.0, "g2"),
            )
        ]
        changed = omr_extract.normalize_sequential_beam_groups(events)
        self.assertEqual(changed, 0)
        self.assertEqual(events[2]["time"], "1/2")

    def test_musescore_dot_precedes_duration_type(self) -> None:
        voice = ET.Element("voice")
        build_mscx.add_chord(
            voice,
            "eighth",
            1,
            [36],
            "down",
            "dotted-chord",
        )
        build_mscx.add_rest(voice, "eighth", 1, "dotted-rest")
        chord = voice.find("Chord")
        rest = voice.find("Rest")
        self.assertIsNotNone(chord)
        self.assertIsNotNone(rest)
        self.assertEqual(
            [child.tag for child in chord][1:4],
            ["dots", "durationType", "StemDirection"],
        )
        self.assertEqual(
            [child.tag for child in rest][-2:],
            ["dots", "durationType"],
        )

    def test_schema_order_gate_rejects_undotted_duration(self) -> None:
        root = ET.Element("museScore")
        score = ET.SubElement(root, "Score")
        staff = ET.SubElement(score, "Staff")
        measure = ET.SubElement(staff, "Measure")
        voice = ET.SubElement(measure, "voice")
        chord = ET.SubElement(voice, "Chord")
        ET.SubElement(chord, "durationType").text = "eighth"
        ET.SubElement(chord, "dots").text = "1"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "wrong-order.mscx"
            ET.ElementTree(root).write(output, encoding="utf-8")
            with self.assertRaisesRegex(
                RuntimeError,
                "durationType before dots",
            ):
                score_validation.validate_mscx_child_order(output)

    def test_overlapping_tuplet_windows_do_not_leave_partial_tuplet(
        self,
    ) -> None:
        measure = {
            "number": 1,
            "length": 4,
            "events": [
                {
                    "time": time,
                    "pitches": [42],
                    "parts": [
                        {
                            "voice": "up",
                            "pitches": [42],
                            "duration": None,
                            "dots": 0,
                            "beam_group": None,
                        }
                    ],
                }
                for time in ("0", "1/12", "1/6", "1/4")
            ],
            "rests": [],
        }
        operations = build_mscx.voice_operations(measure, 0)
        self.assertEqual(
            [operation[1] for operation in operations],
            [320, 320, 320, 2880],
        )

    def test_mixed_duration_triplet_uses_one_complete_bracket(self) -> None:
        payload = {
            "title": "Mixed triplet",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [36],
                            "parts": [
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                        {
                            "time": "7/24",
                            "pitches": [36],
                            "parts": [
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "eighth",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                        {
                            "time": "3/8",
                            "pitches": [36],
                            "parts": [
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                    ],
                    "rests": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "mixed-tuplet.mscx"
            build_mscx.build(payload, output)
            voice = ET.parse(output).getroot().find(".//Score/Staff/Measure/voice")
            self.assertIsNotNone(voice)
            tuplets = voice.findall("Tuplet")
            self.assertEqual(len(tuplets), 1)
            start = list(voice).index(tuplets[0])
            end = next(
                index
                for index, element in enumerate(list(voice)[start:], start)
                if element.tag == "endTuplet"
            )
            members = [
                element
                for element in list(voice)[start + 1 : end]
                if element.tag in {"Chord", "Rest"}
            ]
            self.assertEqual(
                [
                    (element.tag, element.findtext("durationType"))
                    for element in members
                ],
                [("Rest", "16th"), ("Chord", "eighth")],
            )

    def test_conflicting_rest_uses_overlay_voice(self) -> None:
        events = [
            {"time": "0", "x": 100.0, "review": False, "pitches": [36]},
            {"time": "1/4", "x": 300.0, "review": False, "pitches": [36]},
            {"time": "5/16", "x": 400.0, "review": False, "pitches": [36]},
            {"time": "3/8", "x": 450.0, "review": False, "pitches": [36]},
            {"time": "1/2", "x": 500.0, "review": False, "pitches": [36]},
        ]
        rests = [
            {
                "time": "1/4",
                "x": 320.0,
                "voice": "down",
                "duration": "eighth",
                "dots": 0,
                "review": False,
            }
        ]
        changed = omr_extract.retime_rests_from_events(events, rests, 4)
        self.assertEqual(changed, 0)
        self.assertFalse(rests[0]["review"])
        self.assertEqual(rests[0]["render_voice"], 3)
        self.assertEqual(rests[0]["review_resolution"], "notation-overlay-voice")

    def test_past_bar_rest_moves_left_into_overlay_voice(self) -> None:
        events = [
            {"time": "0", "x": 100.0, "review": False, "pitches": [36]},
            {"time": "1/4", "x": 300.0, "review": False, "pitches": [36]},
            {"time": "1/2", "x": 500.0, "review": False, "pitches": [36]},
            {"time": "3/4", "x": 700.0, "review": False, "pitches": [36]},
            {"time": "15/16", "x": 850.0, "review": False, "pitches": [38]},
        ]
        rests = [
            {
                "time": "13/16",
                "x": 780.0,
                "voice": "down",
                "duration": "quarter",
                "dots": 0,
                "review": True,
                "review_resolution": "rest-past-bar",
            }
        ]
        omr_extract.retime_rests_from_events(
            events,
            rests,
            4,
            use_geometry=False,
        )
        self.assertFalse(rests[0]["review"])
        self.assertEqual(rests[0]["time"], "3/4")
        self.assertEqual(rests[0]["render_voice"], 3)

    def test_resolved_rest_clears_stale_conflict_reason(self) -> None:
        events = [
            {"time": "0", "x": 100.0, "review": False, "pitches": [36]},
            {"time": "1/2", "x": 500.0, "review": False, "pitches": [36]},
        ]
        rests = [
            {
                "time": "1/4",
                "x": 300.0,
                "voice": "down",
                "duration": "quarter",
                "dots": 0,
                "review": True,
                "review_resolution": "rest-overlaps-voice-attack",
            }
        ]
        omr_extract.retime_rests_from_events(
            events,
            rests,
            4,
            use_geometry=False,
        )
        self.assertFalse(rests[0]["review"])
        self.assertEqual(rests[0]["review_resolution"], "structure-confirmed")

    def test_impossible_dotted_rest_rejects_the_augmentation_dot(self) -> None:
        events = [
            {"time": "0", "x": 100.0, "review": False, "pitches": [36]},
            {"time": "1/2", "x": 500.0, "review": False, "pitches": [36]},
            {"time": "1", "x": 900.0, "review": False, "pitches": [36]},
        ]
        rests = [
            {
                "time": "7/8",
                "x": 850.0,
                "voice": "down",
                "duration": "eighth",
                "dots": 1,
                "review": False,
            }
        ]
        omr_extract.retime_rests_from_events(
            events,
            rests,
            4,
            use_geometry=False,
        )
        self.assertFalse(rests[0]["review"])
        self.assertEqual(rests[0]["dots"], 0)
        self.assertEqual(
            rests[0]["review_resolution"],
            "impossible-rest-dot-removed",
        )

    def test_dotted_rest_preserves_dot_in_overlay_voice(self) -> None:
        events = [
            {"time": "0", "x": 100.0, "review": False, "pitches": [36]},
            {"time": "15/16", "x": 800.0, "review": False, "pitches": [36]},
        ]
        rests = [
            {
                "time": "13/16",
                "x": 720.0,
                "voice": "down",
                "duration": "eighth",
                "dots": 1,
                "review": False,
            }
        ]
        omr_extract.retime_rests_from_events(
            events,
            rests,
            4,
            use_geometry=False,
        )
        self.assertFalse(rests[0]["review"])
        self.assertEqual(rests[0]["dots"], 1)
        self.assertEqual(rests[0]["render_voice"], 3)
        self.assertEqual(
            rests[0]["review_resolution"],
            "augmentation-rest-overlay",
        )

    def test_overlay_rest_is_emitted_without_moving_notes(self) -> None:
        payload = {
            "title": "Overlay rest",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [
                        {
                            "time": "0",
                            "pitches": [36],
                            "parts": [
                                {
                                    "voice": "down",
                                    "pitches": [36],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                        {
                            "time": "1/2",
                            "pitches": [42],
                            "parts": [
                                {
                                    "voice": "up",
                                    "pitches": [42],
                                    "duration": "quarter",
                                    "dots": 0,
                                    "beam_group": None,
                                }
                            ],
                        },
                    ],
                    "rests": [
                        {
                            "time": "0",
                            "voice": "down",
                            "duration": "quarter",
                            "dots": 0,
                            "review": False,
                            "render_voice": 3,
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "overlay-rest.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            voices = root.findall(".//Staff/Measure/voice")
            self.assertEqual(len(voices), 4)
            score_validation.validate_score_structure(output, payload)
            score_validation.validate_event_timeline(output, payload)
            score_validation.validate_rest_structure(output, payload)

    def test_musicxml_voices_use_independent_cursors(self) -> None:
        xml = b"""<?xml version="1.0"?>
        <score-partwise>
          <part-list>
            <score-part id="P1">
              <score-instrument id="P1-I36">
                <instrument-name>Bass_Drum_1</instrument-name>
              </score-instrument>
              <score-instrument id="P1-I38">
                <instrument-name>Acoustic_Snare</instrument-name>
              </score-instrument>
            </score-part>
          </part-list>
          <part id="P1">
            <measure number="1">
              <attributes><divisions>4</divisions></attributes>
              <note>
                <unpitched/>
                <duration>8</duration>
                <instrument id="P1-I38"/>
                <voice>1</voice><type>half</type><stem>up</stem>
              </note>
              <note>
                <unpitched/>
                <duration>8</duration>
                <instrument id="P1-I38"/>
                <voice>1</voice><type>half</type><stem>up</stem>
              </note>
              <backup><duration>16</duration></backup>
              <note>
                <unpitched/>
                <duration>4</duration>
                <instrument id="P1-I36"/>
                <voice>2</voice><type>quarter</type><stem>down</stem>
              </note>
              <note>
                <unpitched/>
                <duration>4</duration>
                <instrument id="P1-I36"/>
                <voice>2</voice><type>quarter</type><stem>down</stem>
              </note>
              <note>
                <unpitched/>
                <duration>4</duration>
                <instrument id="P1-I36"/>
                <voice>2</voice><type>quarter</type><stem>down</stem>
              </note>
              <note>
                <unpitched/>
                <duration>4</duration>
                <instrument id="P1-I36"/>
                <voice>2</voice><type>quarter</type><stem>down</stem>
              </note>
            </measure>
          </part>
        </score-partwise>
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("score.xml", xml)
            payload = mxl_extract.extract_page(path, "Test", 100, {1: 4})
        events = payload["measures"][0]["events"]
        by_time = {(event["time"], tuple(event["pitches"])) for event in events}
        self.assertEqual(
            by_time,
            {("0", (36, 38)), ("1/4", (36,)), ("1/2", (36, 38)), ("3/4", (36,))},
        )

    def test_musicxml_accepts_space_separated_drum_names(self) -> None:
        root = ET.fromstring(
            """
            <score-partwise>
              <part-list>
                <score-part id="P1">
                  <score-instrument id="P1-I50">
                    <instrument-name>Crash Cymbal 1</instrument-name>
                  </score-instrument>
                  <score-instrument id="P1-I48">
                    <instrument-name>Low-Mid Tom</instrument-name>
                  </score-instrument>
                </score-part>
              </part-list>
            </score-partwise>
            """
        )
        self.assertEqual(
            mxl_extract.instrument_map(root),
            {"P1-I50": 49, "P1-I48": 47},
        )
        self.assertEqual(
            mxl_extract.instrument_map(root, dbscore_export=True),
            {"P1-I50": 49, "P1-I48": 47},
        )

    def test_musicxml_without_drum_instruments_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "piano.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "score.xml",
                    """<score-partwise>
                      <part-list>
                        <score-part id="P1">
                          <score-instrument id="P1-I1">
                            <instrument-name>Piano</instrument-name>
                          </score-instrument>
                        </score-part>
                      </part-list>
                      <part id="P1"/>
                    </score-partwise>""",
                )
            with self.assertRaisesRegex(ValueError, "仅支持架子鼓鼓谱"):
                mxl_extract.extract_page(path, "Piano", 100, {})

    def test_repeats_and_volta_are_written(self) -> None:
        payload = {
            "title": "Repeat",
            "tempo": 100,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "start_repeat": True,
                    "events": [],
                },
                {
                    "number": 2,
                    "length": 4,
                    "end_repeat": True,
                    "repeat_count": 3,
                    "volta": 1,
                    "events": [],
                },
                {
                    "number": 3,
                    "length": 4,
                    "volta": 2,
                    "events": [],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "repeat.mscx"
            build_mscx.build(payload, output)
            root = ET.parse(output).getroot()
            self.assertIsNotNone(root.find(".//Staff/Measure/startRepeat"))
            self.assertEqual(
                root.findtext(".//Staff/Measure[2]/endRepeat"),
                "3",
            )
            self.assertEqual(len(root.findall(".//SpannerMap/Volta")), 2)
            score_validation.validate_repeat_structure(output, payload)

    def test_repeat_structure_uses_stack_attributes(self) -> None:
        systems_measures = [
            [
                omr_extract.Measure(
                    number=1,
                    left=100,
                    right=500,
                )
            ],
            [
                omr_extract.Measure(
                    number=2,
                    left=198,
                    right=700,
                )
            ],
        ]
        systems = [
            ET.fromstring(
                '<system><stack left="100" right="500" repeat="LEFT"/></system>'
            ),
            ET.fromstring(
                '<system><stack left="198" right="700" '
                'repeat="RIGHT" repeat-count="3"/></system>'
            ),
        ]
        omr_extract.annotate_repeats(systems_measures, systems)
        self.assertTrue(systems_measures[0][0].start_repeat)
        self.assertFalse(systems_measures[0][0].end_repeat)
        self.assertTrue(systems_measures[1][0].end_repeat)
        self.assertEqual(systems_measures[1][0].repeat_count, 3)

    def test_final_barline_without_repeat_dots_is_not_a_repeat(self) -> None:
        systems_measures = [
            [
                omr_extract.Measure(
                    number=1,
                    left=100,
                    right=500,
                )
            ]
        ]
        systems = [
            ET.fromstring(
                """
                <system>
                  <barline shape="THICK_BARLINE">
                    <bounds x="490" y="100" w="8" h="40"/>
                  </barline>
                  <barline shape="THIN_BARLINE">
                    <bounds x="500" y="100" w="2" h="40"/>
                  </barline>
                </system>
                """
            )
        ]
        omr_extract.annotate_repeats(systems_measures, systems)
        self.assertFalse(systems_measures[0][0].end_repeat)

    def test_volta_numbers_continue_across_systems_in_same_repeat(
        self,
    ) -> None:
        systems_measures = [
            [
                omr_extract.Measure(
                    number=1,
                    left=100,
                    right=300,
                    start_repeat=True,
                ),
                omr_extract.Measure(
                    number=2,
                    left=300,
                    right=500,
                    end_repeat=True,
                ),
            ],
            [
                omr_extract.Measure(
                    number=3,
                    left=100,
                    right=300,
                )
            ],
        ]
        systems = [
            ET.fromstring(
                """
                <system>
                  <ending>
                    <bounds x="305" y="20" w="190" h="20"/>
                  </ending>
                </system>
                """
            ),
            ET.fromstring(
                """
                <system>
                  <ending>
                    <bounds x="105" y="20" w="190" h="20"/>
                  </ending>
                </system>
                """
            ),
        ]
        omr_extract.annotate_endings(systems_measures, systems)
        self.assertEqual(systems_measures[0][1].volta, 1)
        self.assertEqual(systems_measures[1][0].volta, 2)

    def test_ending_start_ignores_one_pixel_previous_measure_overlap(
        self,
    ) -> None:
        systems_measures = [
            [
                omr_extract.Measure(
                    number=1,
                    left=100,
                    right=300,
                    start_repeat=True,
                )
            ],
            [
                omr_extract.Measure(number=29, left=100, right=300),
                omr_extract.Measure(
                    number=30,
                    left=300,
                    right=500,
                    end_repeat=True,
                ),
                omr_extract.Measure(number=31, left=500, right=700),
            ],
        ]
        systems = [
            ET.fromstring("<system/>"),
            ET.fromstring(
                """
                <system>
                  <ending>
                    <bounds x="299" y="20" w="199" h="20"/>
                  </ending>
                  <ending>
                    <bounds x="501" y="20" w="199" h="20"/>
                  </ending>
                </system>
                """
            ),
        ]
        omr_extract.annotate_endings(systems_measures, systems)
        self.assertIsNone(systems_measures[1][0].volta)
        self.assertEqual(systems_measures[1][1].volta, 1)
        self.assertEqual(systems_measures[1][2].volta, 2)


if __name__ == "__main__":
    unittest.main()
