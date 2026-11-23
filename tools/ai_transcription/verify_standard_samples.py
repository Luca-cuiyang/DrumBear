#!/usr/bin/env python3
"""Verify the eight approved DB绘谱 drum transcriptions as golden samples."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import score_validation


def canonical_event_digest(db_path: Path, measure_count: int) -> str:
    with zipfile.ZipFile(db_path) as archive:
        name = next(name for name in archive.namelist() if name.endswith(".mscx"))
        data = archive.read(name)
    with tempfile.NamedTemporaryFile(suffix=".mscx") as handle:
        handle.write(data)
        handle.flush()
        events = score_validation.mscx_event_map(
            Path(handle.name),
            {number: 4 for number in range(1, measure_count + 1)},
        )
    canonical = {
        str(measure): {
            str(onset): sorted(pitches)
            for onset, pitches in sorted(events.items())
        }
        for measure, events in sorted(events.items())
    }
    return hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path)
    args = parser.parse_args()

    index = json.loads(args.index.read_text(encoding="utf-8"))
    errors = []
    for item in index["items"]:
        title = item["title"]
        db_path = Path(item["db"])
        certificate_path = Path(item["qualityCertificate"])
        if not db_path.is_file():
            errors.append(f"{title}: missing DB {db_path}")
            continue
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
        db_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
        if db_hash != item["dbSha256"]:
            errors.append(f"{title}: DB hash changed")
        if certificate.get("dbSha256") != db_hash or not certificate.get("passed"):
            errors.append(f"{title}: quality certificate mismatch")
        contract_path = Path(item["measureContract"])
        if not contract_path.is_file():
            errors.append(f"{title}: missing measure contract {contract_path}")
        else:
            contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
            if contract_hash != item["measureContractSha256"]:
                errors.append(f"{title}: measure contract file changed")
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            if contract.get("title") != title:
                errors.append(f"{title}: measure contract title mismatch")
            if int(contract.get("measureCount", -1)) != int(item["measureCount"]):
                errors.append(f"{title}: measure contract count mismatch")
        if canonical_event_digest(db_path, int(item["measureCount"])) != item["eventDigest"]:
            errors.append(f"{title}: event timeline differs from standard")

        with zipfile.ZipFile(db_path) as archive:
            name = next(name for name in archive.namelist() if name.endswith(".mscx"))
            root = ET.fromstring(archive.read(name))
        unwanted = [
            subtype.text
            for subtype in root.findall(".//Articulation/subtype")
            if "Staccato" in (subtype.text or "")
            or "Staccatissimo" in (subtype.text or "")
        ]
        if unwanted:
            errors.append(f"{title}: unwanted articulations {unwanted[:5]}")

    if errors:
        raise SystemExit("Standard sample validation failed:\n" + "\n".join(errors))
    print(f"Validated {len(index['items'])} standard DB绘谱 transcriptions")


if __name__ == "__main__":
    main()
