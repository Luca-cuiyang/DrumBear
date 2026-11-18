#!/usr/bin/env python3
"""Lock and verify every accepted measure against a reviewed contract.

The visual round-trip is an independent sanity check, but it cannot prove that
a source-image review decision was preserved after later normalization.  A
measure contract is the reviewed musical payload with layout coordinates and
diagnostic metadata removed.  Every note, rest, voice, duration, dot, beam
relationship, grace note and structural marker is retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
HERE = Path(__file__).resolve().parent
STANDARD_CONTRACT_DIR = HERE / "standard_contracts"


def _beam_group_names(measure: dict[str, Any]) -> dict[str, str]:
    """Replace unstable source IDs with bar-local ordinal group names."""
    names: dict[str, str] = {}
    for event in measure.get("events", []):
        for part in event.get("parts", []):
            group = part.get("beam_group")
            if group is None:
                continue
            key = str(group)
            if key not in names:
                names[key] = f"beam:{len(names)}"
    return names


def canonical_measure(measure: dict[str, Any]) -> dict[str, Any]:
    beam_names = _beam_group_names(measure)
    events = []
    for event in measure.get("events", []):
        parts = []
        for part in event.get("parts", []):
            group = part.get("beam_group")
            parts.append(
                {
                    "voice": str(part.get("voice") or "up"),
                    "pitches": sorted(int(pitch) for pitch in part.get("pitches", [])),
                    "duration": str(part.get("duration") or "quarter"),
                    "dots": int(part.get("dots") or 0),
                    "beams": int(part.get("beams") or 0),
                    "beam_group": beam_names.get(str(group)) if group is not None else None,
                }
            )
        graces = [
            {
                "pitches": sorted(int(pitch) for pitch in grace.get("pitches", [])),
                "kind": str(grace.get("kind") or "acciaccatura"),
                "voice": str(grace.get("voice") or "up"),
            }
            for grace in event.get("graces", [])
        ]
        canonical_event = {
            "time": str(Fraction(str(event["time"]))),
            "pitches": sorted(int(pitch) for pitch in event.get("pitches", [])),
            "parts": sorted(
                parts,
                key=lambda item: (
                    item["voice"],
                    item["pitches"],
                    item["duration"],
                    item["dots"],
                ),
            ),
            "graces": sorted(
                graces,
                key=lambda item: (item["voice"], item["kind"], item["pitches"]),
            ),
            "articulations": sorted(
                str(articulation)
                for articulation in event.get("articulations", [])
            ),
        }
        ties = sorted(
            (
                str(tie.get("role") or ""),
                str(tie.get("id") or ""),
                int(tie.get("pitch") or 0),
            )
            for tie in event.get("ties", [])
        )
        slurs = sorted(
            (
                str(slur.get("role") or ""),
                str(slur.get("id") or ""),
            )
            for slur in event.get("slurs", [])
        )
        if ties:
            canonical_event["ties"] = ties
        if slurs:
            canonical_event["slurs"] = slurs
        events.append(canonical_event)
    rests = [
        {
            "time": str(Fraction(str(rest["time"]))),
            "voice": str(rest.get("voice") or "up"),
            "duration": str(rest.get("duration") or "quarter"),
            "dots": int(rest.get("dots") or 0),
        }
        for rest in measure.get("rests", [])
    ]
    return {
        "number": int(measure["number"]),
        "length": int(measure["length"]),
        "system_start": bool(measure.get("system_start")),
        "page_start": bool(measure.get("page_start")),
        "start_repeat": bool(measure.get("start_repeat")),
        "end_repeat": bool(measure.get("end_repeat")),
        "repeat_count": max(2, int(measure.get("repeat_count", 2))),
        "volta": measure.get("volta"),
        "events": sorted(events, key=lambda item: (Fraction(item["time"]), item["pitches"])),
        "rests": sorted(
            rests,
            key=lambda item: (
                Fraction(item["time"]),
                0 if item["voice"] == "up" else 1,
                item["duration"],
                item["dots"],
            ),
        ),
    }


def measure_digest(measure: dict[str, Any]) -> str:
    data = json.dumps(
        canonical_measure(measure),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def build_contract(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "title": str(payload["title"]),
        "measureCount": len(payload["measures"]),
        "measures": [
            {
                "number": int(measure["number"]),
                "digest": measure_digest(measure),
            }
            for measure in payload["measures"]
        ],
    }


def compare_contract(
    payload: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    if int(expected.get("schemaVersion", 0)) != SCHEMA_VERSION:
        return [
            f"contract schema {expected.get('schemaVersion')} != {SCHEMA_VERSION}"
        ]
    if str(payload.get("title")) != str(expected.get("title")):
        return [
            f"title {payload.get('title')!r} != {expected.get('title')!r}"
        ]
    actual_measures = payload.get("measures", [])
    expected_measures = expected.get("measures", [])
    if len(actual_measures) != len(expected_measures):
        return [
            f"measure count {len(actual_measures)} != {len(expected_measures)}"
        ]
    errors = []
    for measure, locked in zip(actual_measures, expected_measures):
        number = int(measure["number"])
        if number != int(locked["number"]):
            errors.append(
                f"measure order {number} != {int(locked['number'])}"
            )
            continue
        digest = measure_digest(measure)
        if digest != locked["digest"]:
            errors.append(f"measure {number}: contract digest changed")
    return errors


def contract_path(title: str) -> Path:
    safe_title = re.sub(r"[/:]", "_", title).strip() or "untitled"
    return STANDARD_CONTRACT_DIR / f"{safe_title}.json"


def load_contract(title: str) -> dict[str, Any] | None:
    path = contract_path(title)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def verify_payload_against_standard(payload: dict[str, Any]) -> list[str]:
    expected = load_contract(str(payload["title"]))
    if expected is None:
        return []
    return compare_contract(payload, expected)


def ensure_reviewed_contract(payload: dict[str, Any]) -> tuple[list[str], bool]:
    """Verify a standard contract or lock a newly reviewed score once."""
    expected = load_contract(str(payload["title"]))
    if expected is not None:
        return compare_contract(payload, expected), False
    output = contract_path(str(payload["title"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_contract(payload), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return [], True


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("payload", type=Path)
    build_parser.add_argument("--output", type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("payload", type=Path)
    verify_parser.add_argument("--contract", type=Path)
    args = parser.parse_args()

    if args.command == "build":
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        output = args.output or contract_path(str(payload["title"]))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(build_contract(payload), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote measure contract: {output}")
        return

    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    expected = (
        json.loads(args.contract.read_text(encoding="utf-8"))
        if args.contract is not None
        else load_contract(str(payload["title"]))
    )
    if expected is None:
        raise SystemExit(f"No standard contract for {payload['title']}")
    errors = compare_contract(payload, expected)
    if errors:
        raise SystemExit(
            "Measure contract validation failed:\n" + "\n".join(errors)
        )
    print(f"Validated {len(payload['measures'])} measure contracts")


if __name__ == "__main__":
    main()
