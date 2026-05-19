"""从 .docx / .pdf 提取嵌入图像。

重要：PDF/docx 嵌入大量小尺寸 bitmap（数学符号、字体字形、装饰图标）。
默认过滤掉 < 200×200 px 或 < 8KB 的图像 + 去重（基于 SHA-256），避免
F1/F2 检测器在装饰资产上产生假阳性。

**Raster fallback (2.0.8)**: 现代 publisher PDF (Springer / Nature /
Lancet / Cell Press) 把 figure 存成 vector graphics —— ``page.get_images()``
拿不到。``extract_pdf_images`` 在嵌入位图 < threshold 时,会用
``page.get_pixmap(dpi=150)`` 把每页 render 成 PNG,**包括** vector
figures。这让 F1/F2/F3 在 v5 study 暴露的"PDF 上从不触发"问题终于
能上场。"""
from __future__ import annotations

from pathlib import Path


def extract_pdf_images(
    path: Path,
    out_dir: Path,
    *,
    min_width: int = 200,
    min_height: int = 200,
    min_bytes: int = 8_000,
    raster_fallback: bool = True,
    raster_dpi: int = 150,
    raster_threshold: int = 2,
    raster_max_pages: int = 5,
) -> list[Path]:
    """提取 PDF 嵌入位图,过滤掉太小的(公式/符号/字形片段)。

    优先取嵌入位图(快、像素精确)。当 embedded bitmaps < raster_threshold
    时,**fallback 到 page-as-raster**:用 pymupdf 把每页 render 成 PNG
    (默认 150 dpi)。这覆盖了 Nature/Lancet/Cell Press 的 vector figures
    —— 那些用 page.get_images() 拿不到的图。

    参数:
        raster_fallback: 启用 page-raster fallback (默认 True)
        raster_dpi: render dpi(150 是 figure 检测的合理 balance)
        raster_threshold: 嵌入位图少于这个数就触发 raster fallback
        raster_max_pages: render 最多多少页(防御 100+ 页 PDF 撑爆)
    """
    import hashlib

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
                fp = hashlib.sha256(data).digest()
                if fp in seen:
                    continue
                seen.add(fp)
                ext = base.get("ext", "png")
                dst = out_dir / f"p{page_idx + 1}_img{img_idx + 1}.{ext}"
                dst.write_bytes(data)
                saved.append(dst)

        # Page-as-raster fallback for vector-figure PDFs
        if raster_fallback and len(saved) < raster_threshold:
            n_pages = min(doc.page_count, raster_max_pages)
            for page_idx in range(n_pages):
                page = doc[page_idx]
                matrix = pymupdf.Matrix(raster_dpi / 72, raster_dpi / 72)  # type: ignore[no-untyped-call]
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                raster_data = pix.tobytes("png")  # type: ignore[no-untyped-call]
                if len(raster_data) < min_bytes:
                    continue
                fp = hashlib.sha256(raster_data).digest()
                if fp in seen:
                    continue
                seen.add(fp)
                dst = out_dir / f"raster_p{page_idx + 1}.png"
                dst.write_bytes(raster_data)
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
