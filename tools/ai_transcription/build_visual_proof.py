#!/usr/bin/env python3
"""Render a finished drum-score .db beside its source pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

import run_pipeline


PDFTOPPM_TIMEOUT_SECONDS = 5 * 60


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_page_images(
    manifest: dict,
    output_dir: Path,
    pdftoppm: str,
) -> list[Path]:
    result = []
    for index, page in enumerate(manifest["pages"], 1):
        source = Path(page["image"])
        if source.suffix.lower() != ".pdf":
            result.append(source)
            continue
        prefix = output_dir / f"source-{index}"
        subprocess.run(
            [pdftoppm, "-r", "300", "-png", str(source), str(prefix)],
            check=True,
            timeout=PDFTOPPM_TIMEOUT_SECONDS,
        )
        result.extend(
            sorted(
                output_dir.glob(f"source-{index}-*.png"),
                key=lambda path: int(path.stem.rsplit("-", 1)[-1]),
            )
        )
    return result


def side_by_side(source: Path, rendered: Path, output: Path, title: str) -> None:
    left = Image.open(source).convert("RGB")
    right = Image.open(rendered).convert("RGB")
    target_height = 1600

    def resize(image: Image.Image) -> Image.Image:
        width = max(1, round(image.width * target_height / image.height))
        return image.resize((width, target_height))

    left = resize(left)
    right = resize(right)
    header = 60
    canvas = Image.new(
        "RGB",
        (left.width + right.width + 20, target_height + header),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 18), f"{title} | Source", fill="black")
    draw.text((left.width + 20, 18), "DB绘谱 output", fill="black")
    canvas.paste(left, (0, header))
    canvas.paste(right, (left.width + 20, header))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dbscore", type=Path)
    parser.add_argument(
        "--pdf",
        type=Path,
        help="Reuse a PDF already rendered by the pipeline instead of exporting again.",
    )
    parser.add_argument("--pdftoppm", default="pdftoppm")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = args.output_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    style_path = work_dir / "score_style.mss"
    score_path = work_dir / "score.mscx"
    with zipfile.ZipFile(args.db) as archive:
        style_path.write_bytes(archive.read("score_style.mss"))
        score_name = next(
            name for name in archive.namelist() if name.endswith(".mscx")
        )
        score_path.write_bytes(archive.read(score_name))

    source_pages = source_page_images(manifest, work_dir, args.pdftoppm)
    pdf_path = work_dir / "score.pdf"
    if args.pdf is not None:
        shutil.copy2(args.pdf, pdf_path)
    else:
        if args.dbscore is None:
            raise RuntimeError("--dbscore is required when --pdf is not provided")
        run_pipeline.run_dbscore_pdf(
            args.dbscore,
            ["-S", str(style_path), "-o", str(pdf_path), str(score_path)],
            pdf_path,
        )
    rendered_dir = work_dir / "rendered"
    if rendered_dir.exists():
        shutil.rmtree(rendered_dir)
    rendered_dir.mkdir()
    subprocess.run(
        [
            args.pdftoppm,
            "-r",
            "305",
            "-png",
            str(pdf_path),
            str(rendered_dir / "page"),
        ],
        check=True,
        timeout=PDFTOPPM_TIMEOUT_SECONDS,
    )
    rendered_pages = sorted(
        rendered_dir.glob("page-*.png"),
        key=lambda path: int(path.stem.rsplit("-", 1)[-1]),
    )
    if len(source_pages) != len(rendered_pages):
        raise RuntimeError(
            f"{manifest['title']}: source has {len(source_pages)} pages, "
            f"DB output has {len(rendered_pages)}"
        )

    pairs = []
    for index, (source, rendered) in enumerate(
        zip(source_pages, rendered_pages),
        1,
    ):
        comparison = args.output_dir / f"page-{index}-source-vs-db.png"
        side_by_side(source, rendered, comparison, manifest["title"])
        pairs.append(
            {
                "page": index,
                "source": str(source),
                "rendered": str(rendered),
                "comparison": str(comparison),
            }
        )
    report = {
        "title": manifest["title"],
        "profile": "drum-score",
        "db": str(args.db),
        "dbSha256": sha256(args.db),
        "renderedPdf": str(pdf_path),
        "pages": pairs,
        "pageCountMatches": True,
    }
    (args.output_dir / "visual-proof.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote visual proof: {args.output_dir}")


if __name__ == "__main__":
    main()
