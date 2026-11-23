#!/usr/bin/env python3
"""Batch acceptance test for MIDI Converter and DB绘谱."""

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def read_score(db_path):
    with ZipFile(db_path) as archive:
        score_name = next(
            (name for name in archive.namelist() if name.endswith(".mscx")),
            None,
        )
        if score_name is None:
            raise RuntimeError("DB绘谱 package contains no .mscx score")
        return ElementTree.fromstring(archive.read(score_name))


def run_one(converter, dbscore, source, output_dir, grid, bpm):
    stem = source.stem
    normalized = output_dir / f"{stem}-standard.mid"
    report_path = output_dir / f"{stem}-standard.json"
    db_path = output_dir / f"{stem}.db"
    partial_db_path = output_dir / f"{stem}.partial.db"

    normalized_result = subprocess.run(
        [
            converter,
            "normalize",
            "--input",
            str(source),
            "--output",
            str(normalized),
            "--report",
            str(report_path),
            "--grid",
            grid,
            "--bpm",
            bpm,
            "--overwrite",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if normalized_result.returncode != 0:
        return {
            "file": source.name,
            "status": "NORMALIZE_FAILED",
            "error": normalized_result.stderr.strip(),
        }

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report["valid"]:
        return {
            "file": source.name,
            "status": "INVALID_MIDI",
            "notes": report["sourceNoteOns"],
            "drum_types": report["drumTypeCount"],
            "unmapped": report["unmappedPitches"],
        }

    db_result = subprocess.run(
        [dbscore, "-o", str(partial_db_path), str(normalized)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    verification_result = subprocess.run(
        [
            converter,
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
    if verification_result.returncode != 0:
        return {
            "file": source.name,
            "status": "DBS_PACKAGE_INVALID",
            "error": verification_result.stderr.strip(),
        }

    score = read_score(db_path)
    score_pitches = Counter(int(item.text) for item in score.findall(".//pitch"))
    report_pitches = {
        int(item["pitch"]): int(item["output"])
        for item in report["pitchCounts"]
    }
    ties = len(score.findall(".//Tie"))
    measures = len(score.findall(".//Measure"))

    errors = []
    if score_pitches != report_pitches:
        errors.append("pitch counts differ between MIDI and DB绘谱")
    if sum(score_pitches.values()) != report["outputHits"]:
        errors.append("DB绘谱 note count differs from report")
    if ties:
        errors.append(f"{ties} unexpected ties")

    return {
        "file": source.name,
        "status": "PASS" if not errors else "DBS_CHECK_FAILED",
        "error": "; ".join(errors),
        "notes": report["outputHits"],
        "drum_types": report["drumTypeCount"],
        "grid": report["grid"],
        "bpm": round(report["outputTempoBpm"], 2),
        "measures": measures,
        "ties": ties,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--converter", required=True)
    parser.add_argument("--dbscore", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--grid", default="auto")
    parser.add_argument("--bpm", default="auto")
    args = parser.parse_args()

    converter = str(Path(args.converter).resolve())
    dbscore = str(Path(args.dbscore).resolve())
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".mid", ".midi"}
    )
    if not files:
        raise SystemExit(f"No MIDI files found in {input_dir}")

    rows = []
    for source in files:
        print(f"Testing {source.name} ...", flush=True)
        row = run_one(converter, dbscore, source, output_dir, args.grid, args.bpm)
        rows.append(row)
        print(f"  {row['status']}", flush=True)

    csv_path = output_dir / "results.csv"
    fields = [
        "file", "status", "notes", "drum_types", "grid",
        "bpm", "measures", "ties", "error",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    failures = [row for row in rows if row["status"] != "PASS"]
    print(f"\n{len(rows) - len(failures)}/{len(rows)} passed")
    print(f"Results: {csv_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
