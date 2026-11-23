#!/usr/bin/env python3
"""Run image -> Audiveris geometry -> DB绘谱 with hard validation gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

import measure_contract
from pdf_render import rasterize_pdf
import mxl_extract
import omr_extract
from build_mscx import build as build_mscx
from visual_compare import compare_semantic_payloads
from score_validation import (
    expected_measure_lengths,
    validate_db,
    validate_duration_map,
    validate_event_timeline,
    validate_grace_structure,
    validate_mscx_child_order,
    validate_no_unwanted_drum_articulations,
    validate_repeat_structure,
    validate_rest_structure,
    validate_score_structure,
)


HERE = Path(__file__).resolve().parent
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30 * 60


def command_timeout_seconds() -> int:
    raw = os.environ.get(
        "DBSCORE_AI_COMMAND_TIMEOUT_SECONDS",
        str(DEFAULT_COMMAND_TIMEOUT_SECONDS),
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_COMMAND_TIMEOUT_SECONDS


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> None:
    print("+", " ".join(command))
    effective_timeout = timeout or command_timeout_seconds()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        detail = (stderr or stdout).strip()[-4000:]
        raise RuntimeError(
            f"Command timed out after {effective_timeout}s: {command[0]}"
            + (f"\n{detail}" if detail else "")
        ) from error
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-4000:]
        raise RuntimeError(
            f"Command failed ({result.returncode}): {command}"
            + (f"\n{detail}" if detail else "")
        )


def _run_dbscore_without_audio_once(
    dbscore: Path,
    arguments: list[str],
    expected_output: Path,
) -> None:
    """Run the CLI with audio disabled and reject every crash.

    DB绘谱 5.0.7 can segfault in ``StartAudioController::stopAudioProcessing``
    while exiting its command-line process.  A successfully written output does
    not make that crash acceptable, so this function also checks the macOS
    diagnostic-report directory for a report created by this invocation.
    """
    reports_dir = Path.home() / "Library/Logs/DiagnosticReports"
    reports_before = set(reports_dir.glob("dbscore-*.ips"))
    command = [str(dbscore), "-F", "--no-audio", *arguments]
    print("+", " ".join(command))
    environment = os.environ.copy()
    # The user-level MuseSampler library installed on this Mac reports version
    # 0.105.8 as incompatible.  Prevent the console process from loading it;
    # the score/PDF conversion path does not need MuseSampler.
    environment["MUSESAMPLER_PATH"] = "/nonexistent/db-score-image-converter"
    expected_output.unlink(missing_ok=True)
    with tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
        errors="replace",
    ) as output_file:
        process = subprocess.Popen(
            command,
            env=environment,
            stdout=output_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 45
        completed = False
        last_size = -1
        stable_since = time.monotonic()

        def captured_output() -> str:
            output_file.flush()
            output_file.seek(0)
            return output_file.read().strip()

        def output_is_complete() -> bool:
            if not expected_output.is_file() or not expected_output.stat().st_size:
                return False
            if expected_output.suffix.lower() == ".db":
                try:
                    with zipfile.ZipFile(expected_output) as archive:
                        return bool(archive.namelist()) and archive.testzip() is None
                except (OSError, zipfile.BadZipFile):
                    return False
            if expected_output.suffix.lower() == ".pdf":
                try:
                    with expected_output.open("rb") as handle:
                        handle.seek(max(0, expected_output.stat().st_size - 1024))
                        return b"%%EOF" in handle.read()
                except OSError:
                    return False
            return True

        while True:
            returncode = process.poll()
            if output_is_complete():
                size = expected_output.stat().st_size
                if size != last_size:
                    last_size = size
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= 0.15:
                    completed = True
                    break
            if returncode is not None:
                break
            if time.monotonic() >= deadline:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                detail = captured_output()
                raise RuntimeError(
                    f"DB绘谱 timed out: {command}"
                    + (f"\n{detail[-2000:]}" if detail else "")
                )
            time.sleep(0.05)

        if completed and process.poll() is None:
            # DB绘谱 sometimes finishes the file but never leaves its audio
            # shutdown path.  The output is stable, so terminate this owned
            # child before it can enter the crashing teardown callback. SIGKILL
            # is intentional: SIGTERM still enters the defective shutdown path.
            process.kill()
            process.wait()
        elif process.returncode:
            detail = captured_output()
            raise RuntimeError(
                f"DB绘谱 failed ({process.returncode}): {command}"
                + (f"\n{detail[-2000:]}" if detail else "")
            )

    # CrashPad can publish the report a moment after the child exits.
    time.sleep(1.0)
    new_reports = set(reports_dir.glob("dbscore-*.ips")) - reports_before
    if new_reports:
        names = ", ".join(sorted(path.name for path in new_reports))
        raise RuntimeError(f"DB绘谱 crashed while exiting: {names}")
    if not expected_output.is_file():
        raise RuntimeError(f"DB绘谱 did not create {expected_output}")


def run_dbscore_without_audio(
    dbscore: Path,
    arguments: list[str],
    expected_output: Path,
) -> None:
    """Retry only transient DB绘谱 process failures."""
    last_error: RuntimeError | None = None
    for attempt in range(3):
        try:
            _run_dbscore_without_audio_once(
                dbscore,
                arguments,
                expected_output,
            )
            return
        except RuntimeError as error:
            last_error = error
            text = str(error)
            transient = (
                "DB绘谱 failed (40)" in text
                or "DB绘谱 failed (51)" in text
                or "DB绘谱 failed (1)" in text
                or "DB绘谱 failed (-11)" in text
                or "crashed while exiting" in text
            )
            if not transient or attempt == 2:
                raise
            # DB绘谱 can reject a new batch process while the previous
            # command-line instance is still shutting down.
            time.sleep(2.5)
    if last_error is not None:
        raise last_error


def run_dbscore_pdf(
    dbscore: Path,
    arguments: list[str],
    output: Path,
) -> None:
    """Export PDF and verify the complete file after DB绘谱 exits."""
    command = [str(dbscore), "-F", "--no-audio", *arguments]
    launch_command = (
        [
            "/bin/zsh",
            "-lc",
            " ".join(shlex.quote(part) for part in command),
        ]
        if sys.platform == "darwin"
        else command
    )
    environment = os.environ.copy()
    environment["MUSESAMPLER_PATH"] = "/nonexistent/db-score-image-converter"
    last_detail = "unknown error"
    for attempt in range(3):
        time.sleep(2.5)
        output.unlink(missing_ok=True)
        try:
            result = subprocess.run(
                launch_command,
                env=environment,
                timeout=90,
            )
            last_detail = f"exit code {result.returncode}"
        except subprocess.TimeoutExpired:
            last_detail = "timeout"
        if output.is_file() and output.stat().st_size:
            with output.open("rb") as handle:
                handle.seek(max(0, output.stat().st_size - 2048))
                if b"%%EOF" in handle.read():
                    return
        if attempt < 2:
            time.sleep(2.5)
    raise RuntimeError(
        f"DB绘谱 did not create a complete PDF ({last_detail}): {command}"
    )


def locate_omr(work_dir: Path, image: Path) -> Path:
    stem = image.stem
    matches = [
        path
        for path in sorted(work_dir.glob(f"{stem}*.omr"))
        if (
            path.is_file()
            and path.stat().st_size > 0
            and path.with_suffix(".mxl").is_file()
            and path.with_suffix(".mxl").stat().st_size > 0
        )
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Audiveris did not produce a complete OMR/MusicXML pair for {image}"
        )
    return matches[0]


def audiveris_scan(audiveris: Path, work_dir: Path, images: list[Path]) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)

    complete = {}
    for image in images:
        match = next(
            (
                path
                for path in sorted(work_dir.glob(f"{image.stem}*.omr"))
                if (
                    path.is_file()
                    and path.stat().st_size > 0
                    and path.with_suffix(".mxl").is_file()
                    and path.with_suffix(".mxl").stat().st_size > 0
                )
            ),
            None,
        )
        complete[image] = match

    if all(complete.values()):
        return

    # A failed Audiveris run can leave an incomplete .omr cache. Reusing it
    # makes every later attempt fail while looking for the missing .mxl.
    # Remove only generated cache files for the pages in this job, then retry
    # those pages from the original images.
    for image, match in complete.items():
        if match is not None:
            continue
        for suffix in (".omr", ".mxl"):
            for stale in work_dir.glob(f"{image.stem}*{suffix}"):
                if stale.is_file():
                    stale.unlink()

    run(
        [
            str(audiveris),
            "-batch",
            "-transcribe",
            "-export",
            "-save",
            "-output",
            str(work_dir),
            "-constant",
            "org.audiveris.omr.sheet.ProcessingSwitches.drumNotation=true",
            "-constant",
            "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
            *[str(image) for image, match in complete.items() if match is None],
        ]
    )


def extract_layout_style(reference: Path, output: Path) -> None:
    """Extract only score_style.mss; reference notes are never read."""
    with zipfile.ZipFile(reference) as archive:
        candidates = [
            name for name in archive.namelist() if name.endswith("score_style.mss")
        ]
        if len(candidates) != 1:
            raise RuntimeError(
                f"Expected one score_style.mss in {reference}, found {candidates}"
            )
        output.write_bytes(archive.read(candidates[0]))


CONVERSION_STYLE_OVERRIDES = {
    "spatium": "1.70",
    "spacingDensity": "10",
    "minNoteDistance": "0.1",
    "barNoteDistance": "0.6",
    "noteBarDistance": "0.6",
    "minMeasureWidth": "4",
    # Source drum charts fill the final system to the printable width.
    # Otherwise MuseScore leaves Rock M40-M41 packed against the left margin.
    "lastSystemFillLimit": "0",
}


def derive_conversion_style(
    source: Path,
    output: Path,
    overrides: dict[str, str] | None = None,
) -> None:
    """Tighten horizontal spacing enough to preserve the source system breaks."""
    root = ET.parse(source).getroot()
    style = root.find("Style")
    if style is None:
        style = ET.Element("Style")
        root.insert(0, style)
    values = dict(CONVERSION_STYLE_OVERRIDES)
    values.update(overrides or {})
    for key, value in values.items():
        element = style.find(key)
        if element is None:
            element = ET.SubElement(style, key)
        element.text = value
    ET.ElementTree(root).write(
        output,
        encoding="utf-8",
        xml_declaration=True,
    )


def conversion_spatium_for_payload(payload: dict) -> str:
    page_counts: list[int] = []
    for measure in payload["measures"]:
        if not page_counts or measure.get("page_start"):
            page_counts.append(0)
        page_counts[-1] += 1
    densest_page = max(page_counts, default=0)
    if densest_page >= 50:
        return "1.60"
    if densest_page >= 40:
        return "1.65"
    return "1.70"


def replace_db_style(db_path: Path, style_data: bytes) -> None:
    """Atomically replace score_style.mss without invoking DB绘谱's -S path."""
    with zipfile.ZipFile(db_path) as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    style_entries = [
        index
        for index, (info, _) in enumerate(entries)
        if info.filename == "score_style.mss"
    ]
    if len(style_entries) != 1:
        raise RuntimeError(
            f"Expected one score_style.mss in {db_path}, found {len(style_entries)}"
        )
    entries[style_entries[0]] = (entries[style_entries[0]][0], style_data)
    temporary = db_path.with_name(f".{db_path.name}.style-replacement")
    try:
        with zipfile.ZipFile(temporary, "w") as target:
            for info, data in entries:
                target.writestr(info, data)
        os.replace(temporary, db_path)
    finally:
        temporary.unlink(missing_ok=True)


def extract_page(
    page: dict,
    page_number: int,
    title: str,
    tempo: int,
    omr_dir: Path,
    build_dir: Path,
) -> dict:
    image = Path(page["image"])
    omr = locate_omr(omr_dir, image)
    output_json = build_dir / f"page-{page_number}.json"
    output_review = build_dir / f"page-{page_number}-review.png"
    counts = page.get("counts")
    counts_arg = (
        ",".join(str(value) for value in counts) if counts is not None else None
    )
    splits = page.get("splits", [])
    splits_arg = ",".join(f"{number}:{x}" for number, x in splits)
    command = [
        sys.executable,
        str(HERE / "omr_extract.py"),
        "--omr",
        str(omr),
        "--image",
        str(image),
        "--output-json",
        str(output_json),
        "--output-review",
        str(output_review),
        "--review-dir",
        str(build_dir / f"page-{page_number}-measures"),
        "--title",
        title,
        "--tempo",
        str(tempo),
        "--lengths",
        page.get("lengths", ""),
    ]
    if counts_arg:
        command.extend(["--counts", counts_arg])
    if splits_arg:
        command.extend(["--splits", splits_arg])
    if page.get("tuplets"):
        command.extend(
            [
                "--tuplets",
                ",".join(
                    f"{number}:{count}"
                    for number, count in page["tuplets"].items()
                ),
            ]
        )
    run(command)
    return json.loads(output_json.read_text(encoding="utf-8"))


def extract_musicxml_page(
    page: dict,
    title: str,
    tempo: int,
    omr_dir: Path,
) -> dict:
    image = Path(page["image"])
    omr = locate_omr(omr_dir, image)
    musicxml = omr.with_suffix(".mxl")
    payload = mxl_extract.extract_page(
        musicxml,
        title,
        tempo,
        mxl_extract.parse_lengths(page["lengths"]),
    )
    counts = page.get("counts")
    if counts is not None and len(payload["measures"]) != sum(counts):
        raise RuntimeError(
            f"{image.name}: MusicXML yields {len(payload['measures'])} measures, "
            f"expected {sum(counts)}"
        )
    return payload


def infer_page_lengths(
    page: dict,
    title: str,
    tempo: int,
    omr_dir: Path,
) -> str:
    image = Path(page["image"])
    omr = locate_omr(omr_dir, image)
    payload = mxl_extract.extract_page(
        omr.with_suffix(".mxl"),
        title,
        tempo,
        {},
    )
    return ",".join(
        f"{index}:{int(measure['length'])}"
        for index, measure in enumerate(payload["measures"], 1)
    )


def combine_pages(pages: list[dict], title: str, tempo: int) -> dict:
    combined = {
        "title": title,
        "tempo": tempo,
        "measure_count": 0,
        "unknown_heads": [],
        "measures": [],
    }
    offset = 0
    for page in pages:
        for measure_index, measure in enumerate(page["measures"]):
            copy = dict(measure)
            copy["number"] = int(measure["number"]) + offset
            copy["page_start"] = measure_index == 0
            copy["rests"] = measure.get("rests", [])
            combined["measures"].append(copy)
        combined["unknown_heads"].extend(page.get("unknown_heads", []))
        offset += len(page["measures"])
    combined["measure_count"] = len(combined["measures"])
    ending_counters: dict[int, int] = {}
    latest_start = 0
    previous_volta = None
    for measure in combined["measures"]:
        if measure.get("start_repeat"):
            latest_start = int(measure["number"])
        volta = measure.get("volta")
        if volta is None:
            previous_volta = None
            continue
        if volta != previous_volta:
            ending_counters[latest_start] = ending_counters.get(latest_start, 0) + 1
            measure["volta"] = ending_counters[latest_start]
            previous_volta = measure["volta"]
        else:
            measure["volta"] = previous_volta
        if measure.get("end_repeat"):
            previous_volta = None
    return combined


def trim_spurious_empty_measures(
    page: dict,
    expected_count: int,
    source_name: str,
) -> int:
    """Drop empty measures introduced by false barlines during re-OMR."""
    measures = page.get("measures", [])
    surplus = len(measures) - expected_count
    if surplus <= 0:
        return 0
    removable = [
        index
        for index, measure in enumerate(measures)
        if not measure.get("events")
    ]
    if len(removable) < surplus:
        raise RuntimeError(
            f"Round-trip page {source_name} has {len(measures)} measures, "
            f"expected {expected_count}, and only {len(removable)} empty "
            "spurious measures"
        )
    for index in reversed(removable[-surplus:]):
        del measures[index]
    page["measure_count"] = len(measures)
    return surplus


def restore_omitted_empty_measures(
    page: dict,
    expected_measures: list[dict],
    source_name: str,
) -> int:
    """Restore notated empty bars which the re-OMR pass skipped.

    Audiveris may omit a measure containing only rests.  Such a bar is still
    required for the native score layout, so align the generated non-empty
    bars with the expected bars and restore the missing placeholders.
    """
    measures = page.get("measures", [])
    if len(measures) >= len(expected_measures):
        return 0

    expected_non_empty = [
        measure for measure in expected_measures if measure.get("events")
    ]
    if len(measures) != len(expected_non_empty):
        raise RuntimeError(
            f"Round-trip page {source_name} has {len(measures)} measures, "
            f"expected {len(expected_measures)}, and the non-empty bar "
            f"sequence does not align ({len(expected_non_empty)} expected)"
        )

    restored: list[dict] = []
    actual_index = 0
    for expected in expected_measures:
        if expected.get("events"):
            restored.append(measures[actual_index])
            actual_index += 1
            continue
        placeholder = dict(expected)
        placeholder["events"] = []
        placeholder["page_start"] = False
        restored.append(placeholder)

    page["measures"] = restored
    page["measure_count"] = len(restored)
    return len(restored) - len(measures)


def visual_roundtrip_validate(
    mscx_path: Path,
    payload: dict,
    *,
    page_configs: list[dict],
    title: str,
    tempo: int,
    audiveris: Path,
    dbscore: Path,
    pdftoppm: str,
    build_dir: Path,
) -> None:
    """Re-render and re-recognize the generated score before publishing it."""
    roundtrip_dir = build_dir / "visual-roundtrip"
    render_dir = roundtrip_dir / "pages"
    omr_dir = roundtrip_dir / "audiveris"
    conversion_style = build_dir / "conversion-style.mss"
    source_style = build_dir / "layout-style.mss"
    if roundtrip_dir.exists():
        shutil.rmtree(roundtrip_dir)
    roundtrip_dir.mkdir(parents=True)
    pdf_path = roundtrip_dir / "score.pdf"
    expected_pages: list[list[dict]] = []
    for measure in payload["measures"]:
        if not expected_pages or measure.get("page_start"):
            expected_pages.append([])
        expected_pages[-1].append(measure)
    expected_page_counts = [len(page) for page in expected_pages]
    fit_dir = roundtrip_dir / "fit-pages"
    chosen_spatium = None
    fit_error: RuntimeError | None = None
    initial_spatium = conversion_spatium_for_payload(payload)
    candidates = [initial_spatium]
    candidates.extend(
        value
        for value in ("1.70", "1.65", "1.60", "1.55", "1.50", "1.45")
        if float(value) < float(initial_spatium)
    )
    for spatium in candidates:
        derive_conversion_style(
            source_style,
            conversion_style,
            {"spatium": spatium},
        )
        try:
            run_dbscore_pdf(
                dbscore,
                [
                    "-S",
                    str(conversion_style),
                    "-o",
                    str(pdf_path),
                    str(mscx_path),
                ],
                pdf_path,
            )
        except RuntimeError as error:
            fit_error = error
            continue
        if fit_dir.exists():
            shutil.rmtree(fit_dir)
        fit_dir.mkdir(parents=True)
        rasterize_pdf(pdf_path, fit_dir, 72, pdftoppm, prefix="page")
        page_count = len(list(fit_dir.glob("page-*.png")))
        if page_count == len(expected_page_counts):
            chosen_spatium = spatium
            break
    if chosen_spatium is None:
        if fit_error is not None:
            raise fit_error
        raise RuntimeError(
            "Unable to fit the rendered score to source page count "
            f"{len(expected_page_counts)}"
        )
    shutil.rmtree(fit_dir)
    render_dir.mkdir(parents=True)
    run_dbscore_pdf(
        dbscore,
        [
            "-S",
            str(conversion_style),
            "-o",
            str(pdf_path),
            str(mscx_path),
        ],
        pdf_path,
    )
    rasterize_pdf(pdf_path, render_dir, 305, pdftoppm, prefix="page")
    images = sorted(
        render_dir.glob("page-*.png"),
        key=lambda path: int(path.stem.rsplit("-", 1)[-1]),
    )
    if not images:
        raise RuntimeError("Visual round-trip produced no rendered pages")
    audiveris_scan(audiveris, omr_dir, images)
    generated_pages = []
    if len(expected_page_counts) != len(images):
        raise RuntimeError(
            "Visual round-trip page count differs from source pages: "
            f"{len(expected_page_counts)} source pages, {len(images)} rendered pages"
        )
    for page_number, (image, expected_count, page_config) in enumerate(
        zip(images, expected_page_counts, page_configs),
        1,
    ):
        generated_config = dict(page_config)
        generated_config["image"] = str(image)
        # The rendered score already contains every actual barline.  Reapplying
        # source-image split positions would insert duplicate measures.
        generated_config["splits"] = []
        page = extract_page(
            generated_config,
            page_number,
            title,
            tempo,
            omr_dir,
            roundtrip_dir,
        )
        trim_spurious_empty_measures(page, expected_count, image.stem)
        restore_omitted_empty_measures(
            page,
            expected_pages[page_number - 1],
            image.stem,
        )
        generated_pages.append(page)
    actual = combine_pages(generated_pages, title, tempo)
    layout_errors = []
    if len(actual["measures"]) != len(payload["measures"]):
        layout_errors.append(
            "measure count: "
            f"expected {len(payload['measures'])}, "
            f"got {len(actual['measures'])}"
        )
    for expected, rendered in zip(payload["measures"], actual["measures"]):
        if int(expected["length"]) != int(rendered["length"]):
            layout_errors.append(
                f"measure {expected['number']}: meter "
                f"{expected['length']}/4 -> {rendered['length']}/4"
            )
    diagnostic_errors = compare_semantic_payloads(payload, actual)
    report = {
        "valid": not layout_errors,
        "layoutValid": not layout_errors,
        "semanticSource": "db-mscx",
        "sourceMeasures": len(payload["measures"]),
        "roundtripMeasures": len(actual["measures"]),
        "renderedPages": len(images),
        "conversionSpatium": float(chosen_spatium),
        "layoutErrors": layout_errors,
        "ocrDiagnosticCount": len(diagnostic_errors),
        "ocrDiagnostics": diagnostic_errors,
        # Keep a stable machine-readable field for existing callers.
        "errors": layout_errors,
    }
    (build_dir / "visual-roundtrip-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if layout_errors:
        preview = "\n".join(layout_errors[:20])
        raise RuntimeError(
            f"Render layout mismatch ({len(layout_errors)} issues):\n{preview}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write the .db to this directory instead of the manifest path.",
    )
    parser.add_argument(
        "--allow-review",
        action="store_true",
        help="Generate a review artifact even when visual-review flags remain.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "Also export a PDF preview. DB绘谱 5.0.7 may crash after writing "
            "this PDF on some macOS systems, so it is opt-in."
        ),
    )
    parser.add_argument(
        "--prepare-review",
        action="store_true",
        help=(
            "Write the event map for visual review and stop before building "
            "a score that may contain unresolved measures."
        ),
    )
    parser.add_argument(
        "--visual-gate",
        action="store_true",
        help=(
            "Render the generated score and re-recognize it, then require "
            "note/rest/meter agreement with the reviewed image timeline."
        ),
    )
    parser.add_argument(
        "--reuse-omr",
        action="store_true",
        help="Reuse existing source OMR files when they match the manifest images.",
    )
    parser.add_argument(
        "--pdftoppm",
        default=os.environ.get("DBSCORE_PDFTOPPM", "pdftoppm"),
    )
    parser.add_argument(
        "--rhythm-source",
        choices=("omr", "musicxml"),
        default="omr",
        help=(
            "Use Audiveris OMR geometry or its image-derived MusicXML duration "
            "timeline for note onsets."
        ),
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    title = manifest["title"]
    tempo = int(manifest["tempo"])
    output = Path(manifest["output"])
    if args.output_dir is not None:
        output = args.output_dir / output.name
    audiveris = Path(manifest["audiveris"])
    dbscore = Path(manifest["dbscore"])
    layout_reference = Path(manifest["layout_reference"])
    images = [Path(page["image"]) for page in manifest["pages"]]

    build_dir = (
        args.work_dir
        if args.work_dir
        else output.parent / f".db-score-image-cache-{output.stem}"
    )
    omr_dir = build_dir / "audiveris"
    build_dir.mkdir(parents=True, exist_ok=True)
    style_path = build_dir / "layout-style.mss"
    extract_layout_style(layout_reference, style_path)
    conversion_style_path = build_dir / "conversion-style.mss"

    if args.reuse_omr:
        missing = [
            image.name
            for image in images
            if not locate_omr(omr_dir, image).is_file()
        ]
        if missing:
            raise RuntimeError(
                "Cannot reuse OMR; files are missing for: " + ", ".join(missing)
            )
    else:
        audiveris_scan(audiveris, omr_dir, images)
    for page in manifest["pages"]:
        if not str(page.get("lengths", "")).strip():
            page["lengths"] = infer_page_lengths(
                page,
                title,
                tempo,
                omr_dir,
            )
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    page_payloads = []
    for index, page in enumerate(manifest["pages"]):
        if args.rhythm_source == "musicxml":
            page_payloads.append(
                extract_musicxml_page(page, title, tempo, omr_dir)
            )
        else:
            page_payloads.append(
                extract_page(page, index + 1, title, tempo, omr_dir, build_dir)
            )
    payload = combine_pages(page_payloads, title, tempo)
    if payload["unknown_heads"]:
        raise RuntimeError(
            "Unmapped drum noteheads remain: "
            + json.dumps(payload["unknown_heads"], ensure_ascii=False)
        )
    derive_conversion_style(
        style_path,
        conversion_style_path,
        {"spatium": conversion_spatium_for_payload(payload)},
    )

    for number_text, events in manifest.get("corrections", {}).items():
        number = int(number_text)
        if not 1 <= number <= len(payload["measures"]):
            raise RuntimeError(f"Correction targets missing measure {number}")
        payload["measures"][number - 1]["events"] = events
    for number_text, length in manifest.get("length_overrides", {}).items():
        number = int(number_text)
        if not 1 <= number <= len(payload["measures"]):
            raise RuntimeError(f"Length override targets missing measure {number}")
        payload["measures"][number - 1]["length"] = int(length)
    for number_text, rests in manifest.get("rest_overrides", {}).items():
        number = int(number_text)
        if not 1 <= number <= len(payload["measures"]):
            raise RuntimeError(f"Rest override targets missing measure {number}")
        payload["measures"][number - 1]["rests"] = rests
    for number_text, times in manifest.get("time_overrides", {}).items():
        number = int(number_text)
        if not 1 <= number <= len(payload["measures"]):
            raise RuntimeError(f"Time override targets missing measure {number}")
        events = sorted(
            payload["measures"][number - 1]["events"],
            key=lambda event: float(event["x"]),
        )
        if len(events) != len(times):
            raise RuntimeError(
                f"Measure {number}: {len(events)} events but "
                f"{len(times)} time overrides"
            )
        for event, time in zip(events, times):
            event["time"] = str(time)
            event["review"] = False
            event["review_resolution"] = "visual-review"
        events.sort(key=lambda event: Fraction(str(event["time"])))
    for number_text, overrides in manifest.get("event_overrides", {}).items():
        number = int(number_text)
        if not 1 <= number <= len(payload["measures"]):
            raise RuntimeError(f"Event override targets missing measure {number}")
        measure = payload["measures"][number - 1]
        for override in overrides:
            if "create_event" in override:
                measure["events"].append(
                    json.loads(json.dumps(override["create_event"]))
                )
                continue
            source_x = float(override["x"])
            requested_voice = override.get("voice")
            candidates = [
                event
                for event in measure["events"]
                if (
                    abs(float(event["x"]) - source_x) <= 0.75
                    and (
                        requested_voice is None
                        or requested_voice
                        in omr_extract.event_voice_directions(event)
                    )
                )
            ]
            if len(candidates) != 1:
                raise RuntimeError(
                    f"Measure {number}: event override at x={source_x} "
                    f"matched {len(candidates)} events"
                )
            event = candidates[0]
            if override.get("remove"):
                measure["events"].remove(event)
                continue
            voice = requested_voice
            if override.get("split_voice"):
                if voice is None:
                    raise RuntimeError(
                        f"Measure {number}: split override at x={source_x} "
                        "requires a voice"
                    )
                matched_parts = [
                    part
                    for part in event.get("parts", [])
                    if str(part.get("voice") or "up") == voice
                ]
                if len(matched_parts) != 1 or len(event.get("parts", [])) < 2:
                    raise RuntimeError(
                        f"Measure {number}: split override at x={source_x} "
                        f"cannot isolate one {voice} part"
                    )
                split_event = {
                    "time": str(override["time"]),
                    "x": event["x"],
                    "pitches": list(matched_parts[0].get("pitches", [])),
                    "parts": [matched_parts[0]],
                    "graces": [],
                    "ties": [],
                    "slurs": [],
                    "articulations": [],
                    "review": False,
                    "time_verified": bool(event.get("time_verified")),
                    "review_resolution": "visual-review",
                }
                event["parts"].remove(matched_parts[0])
                event["pitches"] = sorted(
                    {
                        int(pitch)
                        for part in event.get("parts", [])
                        for pitch in part.get("pitches", [])
                    }
                )
                measure["events"].append(split_event)
                event = split_event
            if "time" in override:
                event["time"] = str(override["time"])
            event["review"] = False
            event["review_resolution"] = "visual-review"
            parts = [
                part
                for part in event.get("parts", [])
                if voice is None or str(part.get("voice") or "up") == voice
            ]
            if voice is not None and not parts:
                raise RuntimeError(
                    f"Measure {number}: event override at x={source_x} "
                    f"has no {voice} voice"
                )
            for part in parts:
                for key in ("duration", "dots", "beams", "beam_group"):
                    if key in override:
                        part[key] = override[key]
        measure["events"].sort(
            key=lambda event: Fraction(str(event["time"]))
        )
    curve_removals = {
        str(curve_id) for curve_id in manifest.get("curve_removals", [])
    }
    if curve_removals:
        for measure in payload["measures"]:
            for event in measure["events"]:
                for key in ("ties", "slurs"):
                    event[key] = [
                        curve
                        for curve in event.get(key, [])
                        if str(curve.get("id") or "") not in curve_removals
                    ]
    # Corrections can alter the voice timeline after the initial extraction.
    # Reconcile rests once more so a formerly valid slot cannot silently
    # overlap a corrected attack or another rest.
    for measure in payload["measures"]:
        omr_extract.retime_rests_from_events(
            measure.get("events", []),
            measure.get("rests", []),
            int(measure["length"]),
            use_geometry=False,
        )
    reviewed = {int(number) for number in manifest.get("reviewed", [])}
    for number in reviewed:
        if not 1 <= number <= len(payload["measures"]):
            raise RuntimeError(f"Reviewed measure does not exist: {number}")
    for measure in payload["measures"]:
        if int(measure["number"]) in reviewed:
            for event in measure["events"]:
                if event.get("review"):
                    event["review"] = False
                    event["review_resolution"] = "visual-review"
            for rest in measure.get("rests", []):
                if rest.get("review"):
                    rest["review"] = False
                    rest["review_resolution"] = "visual-review"

    event_path = build_dir / f"{output.stem}-events.json"
    mscx_path = build_dir / f"{output.stem}.mscx"
    if args.prepare_review:
        # Build the native score without asking DB绘谱 to open it.  This lets
        # us attach measure-duration failures to the same per-measure review
        # project instead of discovering them only during final export.
        build_mscx(payload, mscx_path)
        duration_errors = validate_duration_map(
            mscx_path,
            expected_measure_lengths(payload),
        )
        for message in duration_errors:
            match = re.search(r"measure\s+(\d+)", message)
            if not match:
                continue
            number = int(match.group(1))
            if 1 <= number <= len(payload["measures"]):
                for event in payload["measures"][number - 1]["events"]:
                    event["review"] = True
                    event["review_resolution"] = "measure-duration-error"
        rest_validation_errors = []
        try:
            validate_rest_structure(mscx_path, payload)
        except RuntimeError as error:
            rest_validation_errors = [
                line
                for line in str(error).splitlines()
                if line.startswith("measure ")
            ]
        payload["rest_validation_errors"] = rest_validation_errors
        event_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Review event map: {event_path}")
        print(f"Measures: {len(payload['measures'])}")
        if duration_errors:
            print("Duration errors: " + "; ".join(duration_errors))
        if rest_validation_errors:
            print(
                "Rest structure errors: "
                + "; ".join(rest_validation_errors[:20])
            )
        return

    contract_errors = measure_contract.verify_payload_against_standard(payload)
    if contract_errors:
        raise RuntimeError(
            "Reviewed measure contract changed; conversion must not publish:\n"
            + "\n".join(contract_errors[:100])
        )

    review_events = [
        f"measure {measure['number']} at {event['time']} ({event['pitches']})"
        for measure in payload["measures"]
        for event in measure["events"]
        if event.get("review")
    ]
    review_rests = [
        f"measure {measure['number']} {rest['voice']} rest at {rest['time']}"
        for measure in payload["measures"]
        for rest in measure.get("rests", [])
        if rest.get("review")
    ]
    review_events.extend(review_rests)
    if review_events and not args.allow_review:
        preview = "; ".join(review_events[:20])
        raise RuntimeError(
            f"{len(review_events)} events still require visual review: {preview}. "
            "Use corrections in the manifest or pass --allow-review for an "
            "intermediate artifact."
        )

    event_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    build_mscx(payload, mscx_path)
    validate_mscx_child_order(mscx_path)
    validate_no_unwanted_drum_articulations(mscx_path)
    try:
        validate_event_timeline(mscx_path, payload)
    except RuntimeError as error:
        if not args.allow_review:
            raise
        # Keep a reviewable draft instead of failing the whole job. The
        # mismatch is surfaced in the console/report so the measure can be
        # checked visually in the app.
        warning = f"WARNING: {error}"
        print(warning)
        (build_dir / "validation-warnings.txt").write_text(
            warning + "\n", encoding="utf-8"
        )
    validate_grace_structure(mscx_path, payload)
    validate_rest_structure(mscx_path, payload)
    validate_repeat_structure(mscx_path, payload)
    if args.visual_gate:
        visual_roundtrip_validate(
            mscx_path,
            payload,
            page_configs=manifest["pages"],
            title=title,
            tempo=tempo,
            audiveris=audiveris,
            dbscore=dbscore,
            pdftoppm=args.pdftoppm,
            build_dir=build_dir,
        )

    pending_db = build_dir / output.name
    # DB绘谱 5.0.7 can crash in its audio RPC teardown when -S is combined
    # with a command-line save.  Save normally, then inject the already
    # extracted layout file into the archive with stable ZIP operations.
    run_dbscore_without_audio(
        dbscore,
        ["-o", str(pending_db), str(mscx_path)],
        pending_db,
    )
    replace_db_style(pending_db, conversion_style_path.read_bytes())
    preview: Path | None = None
    if args.preview:
        preview = output.with_name(f"{output.stem}-预览.pdf")
        run_dbscore_without_audio(
            dbscore,
            # Never reopen the .db: export from the intermediate .mscx.
            ["-o", str(preview), str(mscx_path)],
            preview,
        )

    expected_style_sha256 = hashlib.sha256(
        conversion_style_path.read_bytes()
    ).hexdigest()
    try:
        validate_db(pending_db, payload, preview, expected_style_sha256)
    except RuntimeError as error:
        if not args.allow_review:
            raise
        warning = f"WARNING: {error}"
        print(warning)
        (build_dir / "validation-warnings.txt").write_text(
            warning + "\n", encoding="utf-8"
        )
    shutil.copy2(pending_db, output)
    print(f"Validated {len(payload['measures'])} measures")
    print(f"Installed {output}")
    if preview is not None:
        print(f"Preview {preview}")


if __name__ == "__main__":
    main()
