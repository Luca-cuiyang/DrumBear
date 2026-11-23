#!/usr/bin/env python3
"""End-to-end verification of MIDI Converter output in a DB绘谱 file."""

import argparse
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def score_xml_path(db_path):
    with ZipFile(db_path) as archive:
        names = archive.namelist()
    candidates = [name for name in names if name.endswith(".mscx")]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one .mscx in {db_path}, found {len(candidates)}")
    return candidates[0]


def read_score(db_path):
    with ZipFile(db_path) as archive:
        name = score_xml_path(db_path)
        root = ElementTree.fromstring(archive.read(name))
    return root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--converter", required=True)
    parser.add_argument("--dbscore", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--grid", default="auto")
    parser.add_argument("--bpm", default="auto")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        normalized = root / "standard.mid"
        report_path = root / "report.json"
        partial_db_path = root / "partial.db"
        db_path = root / "result.db"

        normalize = subprocess.run(
            [
                args.converter,
                "normalize",
                "--input",
                args.input,
                "--output",
                str(normalized),
                "--report",
                str(report_path),
                "--grid",
                args.grid,
                "--bpm",
                args.bpm,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if normalize.returncode != 0:
            raise SystemExit(f"normalization failed:\n{normalize.stderr}")

        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not report["valid"]:
            raise SystemExit(f"normalization report is invalid: {report}")

        convert = subprocess.run(
            [args.dbscore, "-o", str(partial_db_path), str(normalized)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        verify = subprocess.run(
            [
                args.converter,
                "verify-db",
                "--input",
                str(partial_db_path),
                "--move-to",
                str(db_path),
                "--discard-on-failure",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if verify.returncode != 0:
            raise SystemExit(
                "DB绘谱 package verification failed:\n"
                f"{verify.stderr}\nconverter output:\n{convert.stderr}"
            )

        score = read_score(db_path)
        score_pitches = Counter(int(item.text) for item in score.findall(".//pitch"))
        report_pitches = {
            int(item["pitch"]): int(item["output"])
            for item in report["pitchCounts"]
        }
        ties = score.findall(".//Tie")
        measures = score.findall(".//Measure")
        time_signatures = [
            (int(item.findtext("sigN")), int(item.findtext("sigD")))
            for item in score.findall(".//TimeSig")
        ]
        tempos = [float(item.text) for item in score.findall(".//tempo")]

        if score_pitches != report_pitches:
            raise SystemExit(
                "drum pitch counts differ between normalized MIDI and DB绘谱:\n"
                f"report={dict(sorted(report_pitches.items()))}\n"
                f"score={dict(sorted(score_pitches.items()))}"
            )
        if sum(score_pitches.values()) != report["outputHits"]:
            raise SystemExit("DB绘谱 note count differs from the normalization report")
        if ties:
            raise SystemExit(f"DB绘谱 contains {len(ties)} unexpected drum ties")

        print("valid=true")
        print(f"source_note_ons={report['sourceNoteOns']}")
        print(f"exact_duplicates_removed={report['exactDuplicatesRemoved']}")
        print(f"output_hits={report['outputHits']}")
        print(f"drum_types={report['drumTypeCount']}")
        print(f"source_bpm={report['sourceTempoBpm']:.3f}")
        print(f"output_bpm={report['outputTempoBpm']:.3f}")
        print(f"grid={report['grid']}")
        print(f"measures={len(measures)}")
        print(f"ties={len(ties)}")
        print(f"time_signatures={time_signatures[:3]}")
        print(f"tempos={tempos[:3]}")
        print("pitches=" + ",".join(
            f"{pitch}:{count}" for pitch, count in sorted(score_pitches.items())))


if __name__ == "__main__":
    main()
