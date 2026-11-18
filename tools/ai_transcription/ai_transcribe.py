#!/usr/bin/env python3
"""Unified AI transcription entry point used by the DB Score AI page."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import measure_contract
from midi_to_db import convert_midi
from score_validation import validate_curve_structure


HERE = Path(__file__).resolve().parent
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class JobError(RuntimeError):
    pass


def stage(message: str) -> None:
    print(f"STAGE|{message}", flush=True)


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    print("RUN|" + json.dumps(command, ensure_ascii=False), flush=True)
    result = subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        exception_lines = [
            line.strip()
            for line in detail.splitlines()
            if line.strip().startswith(
                ("RuntimeError:", "ValueError:", "FileNotFoundError:")
            )
        ]
        if exception_lines:
            detail = exception_lines[-1]
        raise JobError(
            f"Command failed ({result.returncode}): {command[0]}"
            + (f"\n{detail[-4000:]}" if detail else "")
        )
    return result.stdout


def ensure_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise JobError(f"{label}不存在：{path}")
    return path


def ensure_db_path(path: Path) -> Path:
    if path.suffix.lower() != ".db":
        raise JobError("输出文件必须使用 .db 扩展名")
    return path


def normalize_midi(
    input_path: Path,
    normalized_path: Path,
    report_path: Path,
    converter: Path,
    grid: str,
    bpm: str,
) -> dict:
    stage("正在解析并标准化 MIDI")
    run(
        [
            str(converter),
            "normalize",
            "--input",
            str(input_path),
            "--output",
            str(normalized_path),
            "--report",
            str(report_path),
            "--grid",
            grid,
            "--bpm",
            bpm,
            "--overwrite",
        ]
    )
    if not report_path.is_file():
        raise JobError("MIDI 标准化器没有生成检查报告")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("valid") is not True:
        raise JobError(
            "MIDI 标准化检查未通过："
            + json.dumps(report, ensure_ascii=False)
        )
    return report


def midi_job(args: argparse.Namespace) -> dict:
    input_path = ensure_file(args.input, "MIDI 文件")
    output = ensure_db_path(args.output)
    converter = ensure_file(args.converter, "MIDI 标准化器")
    style = ensure_file(args.style, "DB Score 鼓谱样式")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dbscore-ai-midi-") as temp:
        temp_dir = Path(temp)
        normalized = temp_dir / f"{input_path.stem}.standard.mid"
        normalize_report_path = temp_dir / "normalize-report.json"
        normalize_report = normalize_midi(
            input_path,
            normalized,
            normalize_report_path,
            converter,
            args.grid,
            args.bpm,
        )

        stage("正在生成 DB Score 鼓谱")
        report = convert_midi(
            normalized,
            output,
            style,
            title=args.title or input_path.stem,
            report_path=args.report,
            start_shift=args.start_shift,
            leading_measures=args.leading_measures,
        )
        report["normalize"] = normalize_report
        report["input"] = str(input_path)
        report["source"] = "midi"
        report["strict"] = True
        if args.report is not None:
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        stage("MIDI 转谱完成，逐事件时间轴校验通过")
        return report


def render_pdf(
    pdf_path: Path,
    output_dir: Path,
    pdftoppm: str,
    dpi: int,
) -> list[Path]:
    stage(f"正在渲染 PDF：{pdf_path.name}")
    prefix = output_dir / pdf_path.stem
    run(
        [
            pdftoppm,
            "-r",
            str(dpi),
            "-png",
            str(pdf_path),
            str(prefix),
        ]
    )
    pages = sorted(
        output_dir.glob(f"{pdf_path.stem}-*.png"),
        key=lambda path: int(path.stem.rsplit("-", 1)[-1]),
    )
    if not pages:
        raise JobError(f"PDF 没有渲染出页面：{pdf_path}")
    return pages


def expand_inputs(
    paths: list[Path],
    output_dir: Path,
    pdftoppm: str,
    dpi: int,
) -> list[Path]:
    result: list[Path] = []
    for path in paths:
        ensure_file(path, "鼓谱文件")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            result.extend(render_pdf(path, output_dir, pdftoppm, dpi))
        elif suffix in IMAGE_SUFFIXES:
            result.append(path)
        else:
            raise JobError(f"不支持的鼓谱文件类型：{path.suffix}")
    if not result:
        raise JobError("没有可转换的鼓谱页面")
    return result


def matching_manifest(inputs: list[Path]) -> dict | None:
    selected_names = sorted(path.name for path in inputs)
    for path in sorted((HERE / "manifests").glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        page_names = sorted(
            Path(page["image"]).name
            for page in manifest.get("pages", [])
        )
        if page_names == selected_names:
            return manifest
    return None


def template_layout_reference(template: dict | None, fallback: Path) -> str:
    """Keep a matched score's verified layout when a job is rerun."""
    value = (template or {}).get("layout_reference")
    return str(value) if value else str(fallback)


def all_measures_are_reviewed(
    review_measures: list[dict],
) -> bool:
    return bool(review_measures) and all(
        measure.get("reviewed")
        for measure in review_measures
    )


def write_quality_certificate(
    project_dir: Path,
    output: Path,
    review: dict,
    visual_report: Path,
) -> dict:
    """Write a reproducible audit record for a reviewed drum score."""
    layout = (
        json.loads(visual_report.read_text(encoding="utf-8"))
        if visual_report.is_file()
        else {}
    )
    all_reviewed = (
        len(review.get("measures", []))
        > 0
        and all(
            measure.get("reviewed")
            for measure in review["measures"]
        )
    )
    events_path = project_dir / "work" / f"{output.stem}-events.json"
    contract_errors: list[str] = []
    contract_locked_now = False
    if events_path.is_file():
        payload = json.loads(events_path.read_text(encoding="utf-8"))
        contract_errors, contract_locked_now = (
            measure_contract.ensure_reviewed_contract(payload)
        )
        curve_errors = []
        with zipfile.ZipFile(output) as archive:
            mscx_name = next(
                name for name in archive.namelist() if name.endswith(".mscx")
            )
            with tempfile.NamedTemporaryFile(
                suffix=".mscx",
                delete=False,
            ) as handle:
                handle.write(archive.read(mscx_name))
                mscx_path = Path(handle.name)
        try:
            validate_curve_structure(mscx_path, payload)
        except RuntimeError as error:
            curve_errors = str(error).splitlines()
        finally:
            mscx_path.unlink(missing_ok=True)
    else:
        contract_errors = [f"missing event map: {events_path}"]
        curve_errors = [f"missing event map: {events_path}"]
    checks = {
        "drumOnly": True,
        "allMeasuresReviewed": all_reviewed,
        "noUnresolvedEvents": int(review.get("unresolvedEvents", 0)) == 0,
        "noUnresolvedRests": int(review.get("unresolvedRests", 0)) == 0,
        "measureContractMatches": not contract_errors,
        "curveStructureMatches": not curve_errors,
        "renderPagesMatch": bool(layout.get("layoutValid")),
        "renderMeasureCountMatches": (
            int(layout.get("roundtripMeasures", -1))
            == int(layout.get("sourceMeasures", -2))
        ),
        "semanticSourceIsNativeScore": (
            layout.get("semanticSource") == "db-mscx"
        ),
        "dbExists": output.is_file(),
    }
    digest = (
        hashlib.sha256(output.read_bytes()).hexdigest()
        if output.is_file()
        else None
    )
    certificate = {
        "schemaVersion": 1,
        "profile": "drum-score",
        "title": review.get("title"),
        "output": str(output),
        "dbSha256": digest,
        "totalMeasures": int(
            review.get("totalMeasures", len(review.get("measures", [])))
        ),
        "reviewedMeasures": sum(
            1
            for measure in review.get("measures", [])
            if measure.get("reviewed")
        ),
        "qualityFlaggedMeasures": int(
            review.get("qualityFlaggedMeasureCount", 0)
        ),
        "ocrDiagnosticCount": int(layout.get("ocrDiagnosticCount", 0)),
        "measureContractLockedNow": contract_locked_now,
        "measureContractErrors": contract_errors,
        "curveErrors": curve_errors,
        "checks": checks,
        "passed": all(checks.values()),
    }
    path = project_dir / "quality-certificate.json"
    path.write_text(
        json.dumps(certificate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return certificate


QUALITY_RESOLUTION_LABELS = {
    "note-grid-retime": "拍位已按音符网格自动校正",
    "voice-pulse-x-grid": "声部拍位已按音符头横向脉冲自动恢复",
    "cross-voice-onset-split": "跨声部同拍音符已按音符头位置拆分",
    "sparse-lower-sixteenth-grid": "稀疏底鼓十六分节奏已按附点记谱恢复",
    "sparse-sixteenth-pattern": "稀疏底鼓十六分节奏已按附点记谱恢复",
    "notation-overlay-voice": "重叠休止符已放入独立显示声部",
    "augmentation-rest-overlay": "附点休止符已完整放入显示声部",
    "impossible-rest-dot-removed": "不可能成立的原谱附点已剔除",
    "impossible-rest-dot-overlay": "附点剔除后休止符放入显示声部",
    "rest-overlaps-voice-attack": "休止符与同声部音符存在重叠",
    "rest-overlaps-voice-rest": "两个休止符存在时值重叠",
    "rest-past-bar": "休止符时值超过小节边界",
}

AUTO_VERIFIED_QUALITY_FLAGS = {
    "拍位已按音符网格自动校正",
    "声部拍位已按音符头横向脉冲自动恢复",
    "跨声部同拍音符已按音符头位置拆分",
    "稀疏底鼓十六分节奏已按附点记谱恢复",
    "重叠休止符已放入独立显示声部",
    "可见休止符使用第 3/4 显示声部",
    "包含已有的人工作曲校正",
    "附点休止符已完整放入显示声部",
}


def measure_quality_flags(measure: dict) -> list[str]:
    """Describe every automatic interpretation the reviewer should inspect."""
    flags: set[str] = set()
    for event in measure.get("events", []):
        if event.get("review"):
            flags.add("存在尚未确认的节奏位置")
        resolution = str(event.get("review_resolution") or "")
        if resolution in QUALITY_RESOLUTION_LABELS:
            flags.add(QUALITY_RESOLUTION_LABELS[resolution])
        if event.get("source") == "manual-review":
            flags.add("包含已有的人工作曲校正")
    for rest in measure.get("rests", []):
        if rest.get("review"):
            flags.add("存在尚未确认的休止符")
        resolution = str(rest.get("review_resolution") or "")
        if resolution in QUALITY_RESOLUTION_LABELS:
            flags.add(QUALITY_RESOLUTION_LABELS[resolution])
        if rest.get("render_voice") is not None:
            flags.add("可见休止符使用第 3/4 显示声部")
    if measure.get("start_repeat"):
        flags.add("起始反复")
    if measure.get("end_repeat"):
        flags.add(
            f"结束反复×{max(2, int(measure.get('repeat_count', 2)))}"
        )
    if measure.get("volta") is not None:
        flags.add(f"第{int(measure['volta'])}房")
    return sorted(flags)


def measure_review_flags(quality_flags: list[str]) -> list[str]:
    """Return only signals that still require a human notation decision."""
    return sorted(
        flag
        for flag in quality_flags
        if flag not in AUTO_VERIFIED_QUALITY_FLAGS
        and flag != "起始反复"
        and not flag.startswith("结束反复×")
        and not (
            flag.startswith("第")
            and flag.endswith("房")
        )
    )


def image_job(args: argparse.Namespace) -> dict:
    output = ensure_db_path(args.output)
    audiveris = ensure_file(args.audiveris, "Audiveris OMR 引擎")
    dbscore = ensure_file(args.dbscore, "DB Score 程序")
    style = ensure_file(args.style, "DB Score 鼓谱样式")
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.tempo < 20 or args.tempo > 400:
        raise JobError("BPM 必须在 20 到 400 之间")

    project_dir = args.review_dir or output.with_name(
        f"{output.stem}-AI复核资料"
    )
    project_dir.mkdir(parents=True, exist_ok=True)
    rendered = project_dir / "input-pages"
    rendered.mkdir(parents=True, exist_ok=True)
    images = expand_inputs(
        args.inputs,
        rendered,
        args.pdftoppm,
        args.pdf_dpi,
    )
    template = matching_manifest(images)
    template_pages = {
        Path(page["image"]).name: page
        for page in (template or {}).get("pages", [])
    }
    draft_output = project_dir / "draft.db"
    work_dir = project_dir / "work"
    layout_reference = template_layout_reference(template, style)
    manifest = {
        "profile": "drum-score",
        "title": args.title,
        "tempo": args.tempo,
        "output": str(draft_output),
        "final_output": str(output),
        "audiveris": str(audiveris),
        "dbscore": str(dbscore),
        "layout_reference": layout_reference,
        "pages": [
            {
                "image": str(image),
                "lengths": template_pages.get(image.name, {}).get("lengths", ""),
                "counts": template_pages.get(image.name, {}).get("counts"),
                "splits": template_pages.get(image.name, {}).get("splits", []),
                "tuplets": template_pages.get(image.name, {}).get("tuplets", {}),
            }
            for image in images
        ],
        "corrections": (template or {}).get("corrections", {}),
        "length_overrides": (template or {}).get("length_overrides", {}),
        "rest_overrides": (template or {}).get("rest_overrides", {}),
        "time_overrides": (template or {}).get("time_overrides", {}),
        "reviewed": (template or {}).get("reviewed", []),
    }
    manifest_path = project_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        stage("正在识别鼓谱并重建节奏")
        run(
            [
                sys.executable,
                str(HERE / "run_pipeline.py"),
                str(manifest_path),
                "--work-dir",
                str(work_dir),
                "--allow-review",
                "--prepare-review",
                "--rhythm-source",
                args.rhythm_source,
            ]
        )
    except JobError as error:
        text = str(error)
        if "still require visual review" in text:
            raise JobError(
                "草稿生成阶段仍有未通过结构检查的事件，无法进入人工复核。"
            ) from error
        raise

    event_path = work_dir / "draft-events.json"
    if not event_path.is_file():
        raise JobError("识别完成，但没有生成复核事件表")
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    review_images = sorted(
        work_dir.glob("page-*-review.png"),
        key=lambda path: int(path.stem.split("-")[1]),
    )

    page_index = 0
    page_measure_numbers: list[list[int]] = []
    for measure in payload["measures"]:
        if measure.get("page_start") and (page_measure_numbers or page_index == 0):
            if page_measure_numbers:
                page_index += 1
            page_measure_numbers.append([])
        if not page_measure_numbers:
            page_measure_numbers.append([])
        page_measure_numbers[page_index].append(int(measure["number"]))

    review_measures = []
    unresolved_total = 0
    unresolved_event_total = 0
    unresolved_rest_total = 0
    for measure in payload["measures"]:
        unresolved = [
            {
                "time": str(event["time"]),
                "pitches": event.get("pitches", []),
                "reason": event.get("review_resolution", "unconfirmed-rhythm"),
            }
            for event in measure.get("events", [])
            if event.get("review")
        ]
        unresolved_rests = [
            {
                "time": str(rest["time"]),
                "voice": rest.get("voice", "up"),
                "duration": rest.get("duration", "quarter"),
                "reason": rest.get("review_resolution", "unconfirmed-rest-position"),
            }
            for rest in measure.get("rests", [])
            if rest.get("review")
        ]
        unresolved_event_total += len(unresolved)
        unresolved_rest_total += len(unresolved_rests)
        unresolved_total += len(unresolved) + len(unresolved_rests)
        number = int(measure["number"])
        current_page = next(
            (
                index
                for index, numbers in enumerate(page_measure_numbers)
                if number in numbers
            ),
            0,
        )
        local_measure_index = (
            page_measure_numbers[current_page].index(number) + 1
            if current_page < len(page_measure_numbers)
            else number
        )
        source_crop = (
            work_dir
            / f"page-{current_page + 1}-measures"
            / f"m{local_measure_index:02d}.png"
        )
        quality_flags = measure_quality_flags(measure)
        review_flags = measure_review_flags(quality_flags)
        auto_accepted = not unresolved and not review_flags
        review_measures.append(
            {
                "number": number,
                "page": current_page + 1,
                "length": int(measure["length"]),
                "start_repeat": bool(measure.get("start_repeat")),
                "end_repeat": bool(measure.get("end_repeat")),
                "repeat_count": max(2, int(measure.get("repeat_count", 2))),
                "volta": measure.get("volta"),
                "unresolvedEvents": unresolved,
                "unresolvedRests": unresolved_rests,
                "unresolvedCount": len(unresolved) + len(unresolved_rests),
                "events": measure.get("events", []),
                "rests": measure.get("rests", []),
                "qualityFlags": quality_flags,
                "qualityFlagCount": len(quality_flags),
                "reviewReasons": review_flags,
                "reviewReasonCount": len(review_flags),
                "sourceCrop": str(source_crop),
                "requiresReview": not auto_accepted,
                "autoAccepted": auto_accepted,
                "reviewed": auto_accepted,
            }
        )
    global_structure_errors = []
    by_number = {
        int(measure["number"]): measure
        for measure in review_measures
    }
    for message in payload.get("rest_validation_errors", []):
        match = re.search(r"measure\s+(\d+)", message)
        if match and int(match.group(1)) in by_number:
            measure = by_number[int(match.group(1))]
            measure.setdefault("structureErrors", []).append(message)
            measure["unresolvedCount"] = int(measure["unresolvedCount"]) + 1
            measure["requiresReview"] = True
            measure["autoAccepted"] = False
            measure["reviewed"] = False
            unresolved_total += 1
        else:
            global_structure_errors.append(message)
    unresolved_total += len(global_structure_errors)

    review = {
        "profile": "drum-score",
        "title": args.title,
        "tempo": args.tempo,
        "projectDir": str(project_dir),
        "manifest": str(manifest_path),
        "finalOutput": str(output),
        "originalPages": [str(path) for path in images],
        "generatedPages": [str(path) for path in review_images],
        "pageMeasureNumbers": page_measure_numbers,
        "totalMeasures": len(review_measures),
        "unresolvedTotal": unresolved_total,
        "unresolvedEvents": unresolved_event_total,
        "unresolvedRests": unresolved_rest_total,
        "qualityFlaggedMeasureCount": sum(
            1
            for measure in review_measures
            if measure["qualityFlagCount"]
        ),
        "reviewRequiredMeasureCount": sum(
            1
            for measure in review_measures
            if measure["requiresReview"]
        ),
        "autoAcceptedMeasureCount": sum(
            1
            for measure in review_measures
            if measure["autoAccepted"]
        ),
        "globalStructureErrors": global_structure_errors,
        "measures": review_measures,
    }
    review_path = project_dir / "review.json"
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    all_measures_reviewed = all_measures_are_reviewed(review_measures)
    if unresolved_total == 0 and all_measures_reviewed:
        final_manifest = dict(manifest)
        final_manifest["output"] = str(output)
        final_manifest["reviewed"] = [
            int(measure["number"])
            for measure in review_measures
        ]
        final_manifest_path = project_dir / "final-manifest.json"
        final_manifest_path.write_text(
            json.dumps(final_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(HERE / "run_pipeline.py"),
                str(final_manifest_path),
                "--work-dir",
                str(work_dir),
                "--visual-gate",
                "--pdftoppm",
                args.pdftoppm,
            ]
        )
        if not output.is_file():
            raise JobError("自动识别已完成，但没有生成正式 .db")
        certificate = write_quality_certificate(
            project_dir,
            output,
            review,
            work_dir / "visual-roundtrip-report.json",
        )
        if not certificate["passed"]:
            raise JobError("正式 .db 未通过鼓谱质量证书检查")
        report = {
            "profile": "drum-score",
            "valid": True,
            "reviewRequired": False,
            "source": "image-pdf",
            "strict": True,
            "input": [str(path) for path in args.inputs],
            "renderedPages": [str(path) for path in images],
            "output": str(output),
            "projectDir": str(project_dir),
            "totalMeasures": len(review_measures),
            "autoAcceptedMeasures": sum(
                1
                for measure in review_measures
                if measure["autoAccepted"]
            ),
            "unresolvedTotal": unresolved_total,
            "unresolvedEvents": unresolved_event_total,
            "unresolvedRests": unresolved_rest_total,
            "title": args.title,
            "tempo": args.tempo,
            "rhythmSource": args.rhythm_source,
            "qualityCertificate": certificate,
        }
        stage("图片 / PDF 转谱完成，全部严格校验通过")
    else:
        report = {
            "profile": "drum-score",
            "valid": False,
            "reviewRequired": True,
            "source": "image-pdf",
            "input": [str(path) for path in args.inputs],
            "renderedPages": [str(path) for path in images],
            "output": str(output),
            "finalOutput": str(output),
            "projectDir": str(project_dir),
            "reviewPath": str(review_path),
            "totalMeasures": len(review_measures),
            "autoAcceptedMeasures": sum(
                1
                for measure in review_measures
                if measure["autoAccepted"]
            ),
            "unresolvedTotal": unresolved_total,
            "unresolvedEvents": unresolved_event_total,
            "unresolvedRests": unresolved_rest_total,
            "globalStructureErrors": global_structure_errors,
            "title": args.title,
            "tempo": args.tempo,
            "rhythmSource": args.rhythm_source,
        }
        review_required_count = sum(
            1
            for measure in review_measures
            if measure["requiresReview"]
        )
        if unresolved_total:
            stage(
                f"识别完成，需要复核 {len(review_measures)} 个小节；"
                f"当前有 {unresolved_total} 个事件未唯一确认"
            )
        else:
            stage(
                f"自动结构检查已通过；"
                f"{len(review_measures) - review_required_count} 个小节自动通过，"
                f"仍需核对 {review_required_count} 个小节"
            )
    if args.report is not None:
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def review_finalize_job(args: argparse.Namespace) -> dict:
    project_dir = args.project.resolve()
    review_path = project_dir / "review.json"
    manifest_path = project_dir / "manifest.json"
    if not review_path.is_file() or not manifest_path.is_file():
        raise JobError("复核工程不完整，缺少 review.json 或 manifest.json")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reviewed = {
        int(measure["number"])
        for measure in review.get("measures", [])
        if measure.get("reviewed")
    }
    total = int(review.get("totalMeasures", len(review.get("measures", []))))
    if len(reviewed) != total:
        raise JobError(
            f"还有 {total - len(reviewed)} 个小节没有完成复核，不能生成正式 .db"
        )
    manifest["reviewed"] = sorted(reviewed)
    manifest["corrections"] = {
        str(measure["number"]): measure.get("events", [])
        for measure in review.get("measures", [])
        if measure.get("reviewed")
    }
    manifest["length_overrides"] = {
        str(measure["number"]): int(measure.get("length", 4))
        for measure in review.get("measures", [])
        if measure.get("reviewed")
    }
    manifest["rest_overrides"] = {
        str(measure["number"]): measure.get("rests", [])
        for measure in review.get("measures", [])
        if measure.get("reviewed")
    }
    final_output = Path(manifest["final_output"])
    manifest["output"] = str(final_output)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stage("正在生成正式 DB Score 鼓谱")
    run(
        [
            sys.executable,
            str(HERE / "run_pipeline.py"),
            str(manifest_path),
            "--work-dir",
            str(project_dir / "work"),
            "--visual-gate",
            "--pdftoppm",
            args.pdftoppm,
        ]
    )
    if not final_output.is_file():
        raise JobError("复核完成，但没有生成正式 .db")
    certificate = write_quality_certificate(
        project_dir,
        final_output,
        review,
        project_dir / "work" / "visual-roundtrip-report.json",
    )
    if not certificate["passed"]:
        raise JobError("正式 .db 未通过鼓谱质量证书检查")
    report = {
        "valid": True,
        "reviewRequired": False,
        "source": "image-pdf-reviewed",
        "strict": True,
        "projectDir": str(project_dir),
        "reviewedMeasures": len(reviewed),
        "totalMeasures": total,
        "output": str(final_output),
        "qualityCertificate": certificate,
    }
    if args.report is not None:
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    stage("全部小节复核完成，正式鼓谱已生成")
    return report


def default_style() -> Path:
    bundled = HERE / "drum-style.db"
    if bundled.is_file():
        return bundled
    local = HERE.parent.parent / "share" / "ai_transcription" / "drum-style.db"
    if local.is_file():
        return local
    return bundled


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    midi = subparsers.add_parser("midi")
    midi.add_argument("--input", type=Path, required=True)
    midi.add_argument("--output", type=Path, required=True)
    midi.add_argument("--title")
    midi.add_argument("--converter", type=Path, required=True)
    midi.add_argument("--style", type=Path, default=default_style())
    midi.add_argument("--grid", default="auto")
    midi.add_argument("--bpm", default="auto")
    midi.add_argument(
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
    midi.add_argument("--leading-measures", type=int, default=0)
    midi.add_argument("--report", type=Path)
    midi.set_defaults(handler=midi_job)

    image = subparsers.add_parser("image")
    image.add_argument(
        "--input",
        dest="inputs",
        type=Path,
        action="append",
        required=True,
    )
    image.add_argument("--output", type=Path, required=True)
    image.add_argument("--title", required=True)
    image.add_argument("--tempo", type=int, required=True)
    image.add_argument("--audiveris", type=Path, required=True)
    image.add_argument("--dbscore", type=Path, required=True)
    image.add_argument("--style", type=Path, default=default_style())
    image.add_argument(
        "--rhythm-source",
        choices=("omr", "musicxml"),
        default="omr",
    )
    image.add_argument(
        "--pdftoppm",
        default=os.environ.get("DBSCORE_PDFTOPPM", "pdftoppm"),
    )
    image.add_argument("--pdf-dpi", type=int, default=300)
    image.add_argument("--review-dir", type=Path)
    image.add_argument("--report", type=Path)
    image.set_defaults(handler=image_job)

    review_finalize = subparsers.add_parser("review-finalize")
    review_finalize.add_argument("--project", type=Path, required=True)
    review_finalize.add_argument(
        "--pdftoppm",
        default=os.environ.get("DBSCORE_PDFTOPPM", "pdftoppm"),
    )
    review_finalize.add_argument("--report", type=Path)
    review_finalize.set_defaults(handler=review_finalize_job)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
    except Exception as error:
        report = {
            "valid": False,
            "strict": True,
            "error": str(error),
            "output": str(getattr(args, "output", "")),
        }
        report_path = getattr(args, "report", None)
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(f"ERROR|{error}", flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
