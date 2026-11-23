"""Rasterize PDF pages for the transcription pipeline.

Rendering is done in-process with pypdfium2. It is bundled with DB绘谱 so
desktop installs do not depend on a separately installed poppler/pdftoppm.
pdftoppm remains as a fallback for development environments.
"""

from pathlib import Path
import subprocess
from typing import Optional


def rasterize_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    pdftoppm: str = "",
    prefix: Optional[str] = None,
) -> list[Path]:
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = prefix or pdf_path.stem

    try:
        import pypdfium2 as pdfium
    except ImportError:
        pdfium = None

    if pdfium is not None:
        document = pdfium.PdfDocument(str(pdf_path))
        try:
            scale = float(dpi) / 72.0
            for index in range(len(document)):
                page = document[index]
                bitmap = page.render(scale=scale)
                bitmap.to_pil().save(output_dir / f"{stem}-{index + 1}.png")
                bitmap.close()
                page.close()
        finally:
            document.close()
    else:
        if not pdftoppm:
            raise RuntimeError(
                "缺少 PDF 渲染组件（pypdfium2），请重新安装 DB绘谱"
            )
        subprocess.run(
            [pdftoppm, "-r", str(dpi), "-png", str(pdf_path), str(output_dir / stem)],
            check=True,
        )

    pages = sorted(
        output_dir.glob(f"{stem}-*.png"),
        key=lambda path: int(path.stem.rsplit("-", 1)[-1]),
    )
    if not pages:
        raise RuntimeError(f"PDF 没有渲染出页面：{pdf_path}")
    return pages
