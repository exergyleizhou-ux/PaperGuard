"""OCR-based table extraction for scanned / image-based PDFs.

Fallback strategy when pdfplumber returns no embedded tables:
1. Render each page as a high-DPI image via pymupdf (already a dep).
2. Run Tesseract OCR via pytesseract to extract text with bounding boxes.
3. Cluster text blocks into rows/columns and build DataFrames.

Requires optional dependency: ``pip install paperguard[ocr]``
(pytesseract + Pillow). Tesseract binary must be on PATH.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pymupdf

logger = logging.getLogger(__name__)

_OCR_DPI = 300
_HAS_TESSERACT: bool | None = None


def _check_tesseract() -> bool:
    """Return True if pytesseract + Tesseract binary are available."""
    global _HAS_TESSERACT  # noqa: PLW0603
    if _HAS_TESSERACT is not None:
        return _HAS_TESSERACT
    try:
        import pytesseract  # type: ignore[import-not-found]  # noqa: F401
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
        _HAS_TESSERACT = True
    except Exception:  # noqa: BLE001
        _HAS_TESSERACT = False
    return _HAS_TESSERACT


def _page_to_image(page: Any, dpi: int = _OCR_DPI) -> Any:
    """Render a pymupdf page to a PIL Image."""
    from PIL import Image

    mat = pymupdf.Matrix(dpi / 72, dpi / 72)  # type: ignore[no-untyped-call]
    pix = page.get_pixmap(matrix=mat)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _ocr_page_to_dataframes(
    image: Any,
    page_no: int,
    table_offset: int,
) -> list[tuple[str, pd.DataFrame]]:
    """Run Tesseract on one page image and parse TSV into DataFrames.

    Tesseract ``image_to_data`` returns a TSV with columns:
    level, page_num, block_num, par_num, line_num, word_num,
    left, top, width, height, conf, text.

    We group by block_num — each block that looks tabular (>=2 columns
    and >=2 rows of numeric-ish data) becomes a DataFrame.
    """
    import pytesseract

    tsv_text: str = pytesseract.image_to_data(image)
    lines = tsv_text.strip().split("\n")
    if len(lines) < 2:
        return []

    header = lines[0].split("\t")
    rows_raw = [ln.split("\t") for ln in lines[1:]]

    # Build records
    records: list[dict[str, Any]] = []
    for row in rows_raw:
        if len(row) != len(header):
            continue
        rec = dict(zip(header, row, strict=False))
        text = rec.get("text", "").strip()
        conf = int(rec.get("conf", "-1"))
        if not text or conf < 30:
            continue
        records.append(rec)

    if not records:
        return []

    # Group by block_num -> line_num -> words
    blocks: dict[int, dict[int, list[str]]] = {}
    for rec in records:
        blk = int(rec.get("block_num", 0))
        ln = int(rec.get("line_num", 0))
        blocks.setdefault(blk, {}).setdefault(ln, []).append(
            rec.get("text", ""),
        )

    results: list[tuple[str, pd.DataFrame]] = []
    idx = table_offset
    for blk_num in sorted(blocks):
        blk_lines = blocks[blk_num]
        if len(blk_lines) < 3:
            continue

        # Each line's words become columns
        all_rows = [blk_lines[ln] for ln in sorted(blk_lines)]
        max_cols = max(len(r) for r in all_rows)
        if max_cols < 2:
            continue

        # Pad rows to same width
        padded = [r + [""] * (max_cols - len(r)) for r in all_rows]

        # First row as header
        cols = [c or f"col_{i}" for i, c in enumerate(padded[0])]
        seen: dict[str, int] = {}
        deduped: list[str] = []
        for c in cols:
            if c in seen:
                seen[c] += 1
                deduped.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                deduped.append(c)

        df = pd.DataFrame(padded[1:], columns=deduped)

        # Coerce numeric columns
        for col_name in df.columns:
            coerced = pd.to_numeric(df[col_name], errors="coerce")
            if coerced.notna().sum() >= max(1, len(df) // 2):
                df[col_name] = coerced

        # Only keep if at least one numeric column exists
        if df.select_dtypes(include="number").shape[1] == 0:
            continue

        idx += 1
        name = f"p{page_no}_ocr_table_{idx}"
        results.append((name, df))

    return results


def ocr_pdf_tables(path: Path) -> dict[str, pd.DataFrame]:
    """Extract tables from a scanned PDF via OCR.

    Returns ``{table_name: DataFrame}`` in the same format as
    ``extract_pdf_tables`` so callers can use either interchangeably.

    Returns empty dict if Tesseract is unavailable or no tables found.
    """
    if not _check_tesseract():
        logger.debug("Tesseract not available; OCR extraction skipped.")
        return {}

    out: dict[str, pd.DataFrame] = {}
    doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    try:
        idx = 0
        for page_no in range(doc.page_count):
            page = doc[page_no]
            image = _page_to_image(page)
            tables = _ocr_page_to_dataframes(image, page_no + 1, idx)
            for name, df in tables:
                out[name] = df
                idx += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR extraction failed: %s", exc)
    finally:
        doc.close()  # type: ignore[no-untyped-call]

    return out
