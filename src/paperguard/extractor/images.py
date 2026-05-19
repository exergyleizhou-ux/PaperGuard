"""从 .docx / .pdf 提取嵌入图像。

重要：PDF/docx 嵌入大量小尺寸 bitmap（数学符号、字体字形、装饰图标）。
默认过滤掉 < 200×200 px 或 < 8KB 的图像 + 去重（基于 SHA-256），避免
F1/F2 检测器在装饰资产上产生假阳性。"""
from __future__ import annotations

from pathlib import Path


def extract_pdf_images(
    path: Path,
    out_dir: Path,
    *,
    min_width: int = 200,
    min_height: int = 200,
    min_bytes: int = 8_000,
) -> list[Path]:
    """提取 PDF 中嵌入的位图图像，过滤掉太小的（公式/符号/字形片段）。

    PDF 文件常嵌入大量小尺寸 bitmap（数学符号、特殊字符、装饰），
    它们会污染下游 F1/F2 检测。默认阈值仅保留 ≥ 200×200、≥ 8KB 的位图，
    这是大多数科研图（柱状图、散点图、显微图、WB）的下限。
    """
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    seen: set[bytes] = set()
    doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    try:
        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            for img_idx, info in enumerate(page.get_images(full=True)):  # type: ignore[no-untyped-call]
                xref = info[0]
                base = doc.extract_image(xref)  # type: ignore[no-untyped-call]
                width = int(base.get("width", 0))
                height = int(base.get("height", 0))
                data = base["image"]
                if width < min_width or height < min_height:
                    continue
                if len(data) < min_bytes:
                    continue
                # 同一 xref 在多页出现只保留一次（Nature logo、letterhead 等）
                import hashlib

                fp = hashlib.sha256(data).digest()
                if fp in seen:
                    continue
                seen.add(fp)
                ext = base.get("ext", "png")
                dst = out_dir / f"p{page_idx + 1}_img{img_idx + 1}.{ext}"
                dst.write_bytes(data)
                saved.append(dst)
    finally:
        doc.close()  # type: ignore[no-untyped-call]
    return saved


def extract_docx_images(
    path: Path,
    out_dir: Path,
    *,
    min_bytes: int = 8_000,
) -> list[Path]:
    """同 PDF：过滤 < 8KB 的 docx 嵌入图像（多是图标/icon）。"""
    import zipfile

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    seen: set[bytes] = set()
    import hashlib

    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.startswith("word/media/"):
                continue
            data = z.read(name)
            if len(data) < min_bytes:
                continue
            fp = hashlib.sha256(data).digest()
            if fp in seen:
                continue
            seen.add(fp)
            dst = out_dir / Path(name).name
            dst.write_bytes(data)
            saved.append(dst)
    return saved
