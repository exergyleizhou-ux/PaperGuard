"""W2 — OCR table extraction tests (mocked, no Tesseract needed)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pandas as pd

# Inject a fake pytesseract module so patch() can resolve the target
# even when pytesseract is not installed.
if "pytesseract" not in sys.modules:
    _fake_pytesseract = ModuleType("pytesseract")
    _fake_pytesseract.image_to_data = MagicMock(return_value="")  # type: ignore[attr-defined]
    _fake_pytesseract.get_tesseract_version = MagicMock()  # type: ignore[attr-defined]
    sys.modules["pytesseract"] = _fake_pytesseract

# PIL is only needed by _page_to_image; ensure it's importable
try:
    from PIL import Image  # noqa: F401
except ImportError:
    _fake_pil = ModuleType("PIL")
    _fake_image = ModuleType("PIL.Image")
    _fake_image.open = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    _fake_pil.Image = _fake_image  # type: ignore[attr-defined]
    sys.modules["PIL"] = _fake_pil
    sys.modules["PIL.Image"] = _fake_image

from paperguard.extractor import ocr_tables

# ---- helpers ---------------------------------------------------------------

_FAKE_TSV_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
    "\tleft\ttop\twidth\theight\tconf\ttext"
)


def _tsv_row(
    block: int,
    line: int,
    word: int,
    text: str,
    conf: int = 90,
) -> str:
    return (
        f"5\t1\t{block}\t1\t{line}\t{word}"
        f"\t10\t10\t50\t12\t{conf}\t{text}"
    )


def _build_tsv(rows: list[str]) -> str:
    return "\n".join([_FAKE_TSV_HEADER, *rows])


# A simple 3-row, 3-col table: header + 3 data rows with numbers
_TABLE_TSV = _build_tsv([
    _tsv_row(1, 1, 1, "Name"),
    _tsv_row(1, 1, 2, "Score"),
    _tsv_row(1, 1, 3, "Grade"),
    _tsv_row(1, 2, 1, "Alice"),
    _tsv_row(1, 2, 2, "95"),
    _tsv_row(1, 2, 3, "A"),
    _tsv_row(1, 3, 1, "Bob"),
    _tsv_row(1, 3, 2, "87"),
    _tsv_row(1, 3, 3, "B"),
    _tsv_row(1, 4, 1, "Carol"),
    _tsv_row(1, 4, 2, "72"),
    _tsv_row(1, 4, 3, "C"),
])


# ---- unit tests for _ocr_page_to_dataframes --------------------------------

def test_ocr_page_to_dataframes_basic() -> None:
    """Parse a simple TSV block into one DataFrame."""
    mock_image = MagicMock()
    with patch("pytesseract.image_to_data", return_value=_TABLE_TSV):
        results = ocr_tables._ocr_page_to_dataframes(mock_image, 1, 0)

    assert len(results) == 1
    name, df = results[0]
    assert "ocr_table" in name
    assert len(df) == 3  # 3 data rows
    assert "Score" in df.columns
    assert df["Score"].dtype in ("float64", "int64")


def test_ocr_page_empty_tsv() -> None:
    """When OCR returns no text, return empty list."""
    mock_image = MagicMock()
    with patch("pytesseract.image_to_data", return_value=_FAKE_TSV_HEADER):
        results = ocr_tables._ocr_page_to_dataframes(mock_image, 1, 0)

    assert results == []


def test_ocr_page_low_confidence_filtered() -> None:
    """Low-confidence words (conf < 30) are filtered out."""
    tsv = _build_tsv([
        _tsv_row(1, 1, 1, "Name", conf=10),
        _tsv_row(1, 1, 2, "Val", conf=10),
        _tsv_row(1, 2, 1, "x", conf=10),
        _tsv_row(1, 2, 2, "1", conf=10),
    ])
    mock_image = MagicMock()
    with patch("pytesseract.image_to_data", return_value=tsv):
        results = ocr_tables._ocr_page_to_dataframes(mock_image, 1, 0)

    assert results == []


# ---- integration-level tests for ocr_pdf_tables ----------------------------

def test_ocr_pdf_tables_no_tesseract() -> None:
    """When Tesseract is unavailable, return empty dict gracefully."""
    ocr_tables._HAS_TESSERACT = None  # reset cache
    with patch.object(ocr_tables, "_check_tesseract", return_value=False):
        result = ocr_tables.ocr_pdf_tables(Path("dummy.pdf"))
    assert result == {}


def test_ocr_pdf_tables_with_mock(tmp_path: Path) -> None:
    """Full pipeline with mocked Tesseract."""
    # Create a minimal valid PDF via pymupdf
    pdf_path = tmp_path / "scan.pdf"
    doc = __import__("pymupdf").open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=200, height=100)  # type: ignore[no-untyped-call]
    page.insert_text((10, 30), "placeholder")  # type: ignore[no-untyped-call]
    doc.save(pdf_path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]

    ocr_tables._HAS_TESSERACT = None  # reset cache

    with (
        patch.object(ocr_tables, "_check_tesseract", return_value=True),
        patch("pytesseract.image_to_data", return_value=_TABLE_TSV),
    ):
        result = ocr_tables.ocr_pdf_tables(pdf_path)

    assert len(result) >= 1
    key = next(iter(result))
    assert "ocr_table" in key
    df = result[key]
    assert len(df) == 3
    assert df["Score"].tolist() == [95.0, 87.0, 72.0]


# ---- cli fallback test -----------------------------------------------------

def test_safe_pdf_tables_ocr_fallback(tmp_path: Path) -> None:
    """_safe_pdf_tables falls back to OCR when pdfplumber returns empty."""
    from paperguard.cli import _safe_pdf_tables

    fake_ocr_df = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})

    with (
        patch(
            "paperguard.cli.extract_pdf_tables",
            return_value={},
        ),
        patch(
            "paperguard.extractor.ocr_tables.ocr_pdf_tables",
            return_value={"p1_ocr_table_1": fake_ocr_df},
        ),
    ):
        sheets, err = _safe_pdf_tables(tmp_path / "dummy.pdf")

    assert len(sheets) == 1
    assert "ocr_table" in next(iter(sheets))
    assert err is None


def test_safe_pdf_tables_no_ocr_fallback(tmp_path: Path) -> None:
    """When pdfplumber has tables, OCR is not called."""
    from paperguard.cli import _safe_pdf_tables

    native_df = pd.DataFrame({"a": [1], "b": [2]})
    ocr_mock = MagicMock()

    with (
        patch(
            "paperguard.cli.extract_pdf_tables",
            return_value={"p1_table_1": native_df},
        ),
        patch(
            "paperguard.extractor.ocr_tables.ocr_pdf_tables",
            ocr_mock,
        ),
    ):
        sheets, err = _safe_pdf_tables(tmp_path / "dummy.pdf")

    assert len(sheets) == 1
    ocr_mock.assert_not_called()
