#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import ai_transcribe
import measure_contract
import visual_compare


class ImageReviewTests(unittest.TestCase):
    def test_existing_manifest_keeps_its_layout_reference(self) -> None:
        self.assertEqual(
            ai_transcribe.template_layout_reference(
                {"layout_reference": "/scores/reference.db"},
                Path("/fallback/style.db"),
            ),
            "/scores/reference.db",
        )
        self.assertEqual(
            ai_transcribe.template_layout_reference(
                {},
                Path("/fallback/style.db"),
            ),
            "/fallback/style.db",
        )

    def test_image_job_requires_every_measure_to_be_reviewed(self) -> None:
        measures = [{"number": 1}, {"number": 2}]
        self.assertFalse(
            ai_transcribe.all_measures_are_reviewed(measures)
        )
        self.assertTrue(
            ai_transcribe.all_measures_are_reviewed(
                [
                    {"number": 1, "reviewed": True},
                    {"number": 2, "reviewed": True},
                ],
            )
        )

    def test_measure_quality_flags_explain_automatic_decisions(self) -> None:
        measure = {
            "events": [
                {
                    "review": False,
                    "review_resolution": "note-grid-retime",
                },
                {
                    "review": False,
                    "review_resolution": "voice-pulse-x-grid",
                },
                {
                    "review": False,
                    "review_resolution": "cross-voice-onset-split",
                },
                {
                    "review": False,
                    "review_resolution": "sparse-lower-sixteenth-grid",
                },
            ],
            "rests": [
                {
                    "review": False,
                    "review_resolution": "notation-overlay-voice",
                    "render_voice": 3,
                }
            ],
        }
        flags = ai_transcribe.measure_quality_flags(measure)
        self.assertIn("拍位已按音符网格自动校正", flags)
        self.assertIn("声部拍位已按音符头横向脉冲自动恢复", flags)
        self.assertIn("跨声部同拍音符已按音符头位置拆分", flags)
        self.assertIn("稀疏底鼓十六分节奏已按附点记谱恢复", flags)
        self.assertIn("重叠休止符已放入独立显示声部", flags)
        self.assertIn("可见休止符使用第 3/4 显示声部", flags)

    def test_structural_auto_corrections_do_not_require_manual_review(self) -> None:
        flags = [
            "拍位已按音符网格自动校正",
            "重叠休止符已放入独立显示声部",
            "可见休止符使用第 3/4 显示声部",
        ]
        self.assertEqual(ai_transcribe.measure_review_flags(flags), [])
        self.assertEqual(
            ai_transcribe.measure_review_flags(
                flags + ["不可能成立的原谱附点已剔除"]
            ),
            ["不可能成立的原谱附点已剔除"],
        )
        repeat_flags = ai_transcribe.measure_quality_flags(
            {
                "start_repeat": True,
                "end_repeat": True,
                "repeat_count": 3,
                "volta": 2,
            }
        )
        self.assertEqual(
            repeat_flags,
            ["第2房", "结束反复×3", "起始反复"],
        )
        self.assertEqual(ai_transcribe.measure_review_flags(repeat_flags), [])

    def test_quality_certificate_requires_review_and_layout_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "score.db"
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("score.mscx", "<museScore/>")
            visual = root / "visual.json"
            visual.write_text(
                json.dumps(
                    {
                        "layoutValid": True,
                        "sourceMeasures": 1,
                        "roundtripMeasures": 1,
                        "semanticSource": "db-mscx",
                        "ocrDiagnosticCount": 12,
                    }
                ),
                encoding="utf-8",
            )
            review = {
                "title": "Test",
                "totalMeasures": 1,
                "unresolvedEvents": 0,
                "unresolvedRests": 0,
                "qualityFlaggedMeasureCount": 1,
                "measures": [{"number": 1, "reviewed": True}],
            }
            work = root / "work"
            work.mkdir()
            (work / "score-events.json").write_text(
                json.dumps(
                    {
                        "title": "Test",
                        "measures": [
                            {
                                "number": 1,
                                "length": 4,
                                "events": [],
                                "rests": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(
                measure_contract,
                "ensure_reviewed_contract",
                return_value=([], True),
            ), patch.object(
                ai_transcribe,
                "validate_curve_structure",
            ):
                certificate = ai_transcribe.write_quality_certificate(
                    root,
                    output,
                    review,
                    visual,
                )
            self.assertTrue(certificate["passed"])
            self.assertEqual(certificate["reviewedMeasures"], 1)
            self.assertTrue((root / "quality-certificate.json").is_file())

    def write_project(self, root: Path, reviewed: bool) -> Path:
        project = root / "review"
        project.mkdir()
        final_output = root / "final.db"
        manifest = {
            "output": str(project / "draft.db"),
            "final_output": str(final_output),
            "reviewed": [],
            "corrections": {},
        }
        event = {
            "time": "1/8",
            "pitches": [36, 42],
            "parts": [],
            "review": False,
        }
        review = {
            "title": "Test",
            "totalMeasures": 1,
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "reviewed": reviewed,
                    "events": [event],
                }
            ],
        }
        (project / "manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        (project / "review.json").write_text(
            json.dumps(review),
            encoding="utf-8",
        )
        return project

    def test_finalize_rejects_incomplete_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.write_project(root, reviewed=False)
            args = argparse.Namespace(
                project=project,
                report=None,
                pdftoppm="pdftoppm",
            )
            with self.assertRaisesRegex(ai_transcribe.JobError, "没有完成复核"):
                ai_transcribe.review_finalize_job(args)

    def test_finalize_passes_edited_events_as_manifest_corrections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.write_project(root, reviewed=True)
            final_output = root / "final.db"

            def fake_run(command: list[str], **_kwargs: object) -> str:
                self.assertTrue(
                    any(item.endswith("/review/manifest.json") for item in command)
                )
                with zipfile.ZipFile(final_output, "w") as archive:
                    archive.writestr("score.mscx", "<museScore/>")
                visual_report = project / "work" / "visual-roundtrip-report.json"
                visual_report.parent.mkdir()
                visual_report.write_text(
                    json.dumps(
                        {
                            "layoutValid": True,
                            "sourceMeasures": 1,
                            "roundtripMeasures": 1,
                            "semanticSource": "db-mscx",
                        }
                    ),
                    encoding="utf-8",
                )
                (project / "work" / "final-events.json").write_text(
                    json.dumps(
                        {
                            "title": "Test",
                            "measures": [
                                {
                                    "number": 1,
                                    "length": 4,
                                    "events": [
                                        json.loads(
                                            (project / "manifest.json").read_text(
                                                encoding="utf-8"
                                            )
                                        )["corrections"]["1"][0]
                                    ],
                                    "rests": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return ""

            with (
                patch.object(ai_transcribe, "run", side_effect=fake_run),
                patch.object(
                    measure_contract,
                    "ensure_reviewed_contract",
                    return_value=([], True),
                ),
                patch.object(
                    ai_transcribe,
                    "validate_curve_structure",
                ),
            ):
                report = ai_transcribe.review_finalize_job(
                    argparse.Namespace(
                        project=project,
                        report=None,
                        pdftoppm="pdftoppm",
                    )
                )
            self.assertTrue(report["valid"])
            manifest = json.loads(
                (project / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["reviewed"], [1])
            self.assertEqual(
                manifest["corrections"]["1"][0]["time"],
                "1/8",
            )
            self.assertEqual(
                manifest["corrections"]["1"][0]["pitches"],
                [36, 42],
            )

    def test_visual_semantic_gate_compares_notes_and_rests(self) -> None:
        payload = {
            "measures": [
                {
                    "number": 1,
                    "length": 4,
                    "events": [{"time": "0", "pitches": [36, 42]}],
                    "rests": [
                        {
                            "time": "1/8",
                            "voice": "up",
                            "duration": "eighth",
                            "dots": 0,
                        }
                    ],
                }
            ]
        }
        same = json.loads(json.dumps(payload))
        self.assertEqual(
            visual_compare.compare_semantic_payloads(payload, same),
            [],
        )
        same["measures"][0]["rests"][0]["voice"] = "down"
        errors = visual_compare.compare_semantic_payloads(payload, same)
        self.assertTrue(
            any("rest difference" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
