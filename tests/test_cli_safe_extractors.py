"""Regression tests for the safe PDF extractor wrappers in CLI.

PDF extractors (``extract_pdf_tables``, ``extract_pdf_text``) raise
``PdfminerException`` and friends on malformed PDFs — for example
when an HTML landing page is mis-served with a ``.pdf`` extension.
The CLI wraps both calls in ``_safe_pdf_tables`` / ``_safe_pdf_text``
so a bad input file never crashes the scan; the scan just records the
error in the audit log and continues with whatever detectors can run.

Found while running the v1 recall pilot — 3 of 5 real publisher OA
"PDFs" were actually HTML landing pages and exited the CLI non-zero,
which would derail any large-scale batch study.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from paperguard.cli import _safe_pdf_tables, _safe_pdf_text


def _write_bytes(p: Path, data: bytes) -> Path:
    p.write_bytes(data)
    return p


def test_safe_pdf_tables_on_html_page(tmp_path: Path) -> None:
    """An HTML page served as .pdf must not crash the scan."""
    bad = _write_bytes(
        tmp_path / "fake.pdf",
        b"<!DOCTYPE html><html><body><h1>404 Not Found</h1></body></html>",
    )
    sheets, err = _safe_pdf_tables(bad)
    assert sheets == {}
    assert err is not None
    assert "PdfminerException" in err or "PDFSyntaxError" in err or "No /Root" in err


def test_safe_pdf_text_on_html_page(tmp_path: Path) -> None:
    """The contract is "never raise", not "return empty". pymupdf is
    tolerant enough to read garbage out of HTML; that's fine, as long
    as control flow returns normally."""
    bad = _write_bytes(
        tmp_path / "fake.pdf",
        b"<!DOCTYPE html><html><body><h1>404</h1></body></html>",
    )
    text, err = _safe_pdf_text(bad)
    assert isinstance(text, str)  # never raise
    assert err is None or isinstance(err, str)


def test_safe_pdf_tables_on_empty_file(tmp_path: Path) -> None:
    bad = _write_bytes(tmp_path / "empty.pdf", b"")
    sheets, err = _safe_pdf_tables(bad)
    assert sheets == {}
    assert err is not None


def test_safe_pdf_text_on_empty_file(tmp_path: Path) -> None:
    bad = _write_bytes(tmp_path / "empty.pdf", b"")
    text, err = _safe_pdf_text(bad)
    assert text == ""


def test_safe_pdf_tables_on_truncated_pdf(tmp_path: Path) -> None:
    # ``%PDF-`` header present but body lopped off
    bad = _write_bytes(tmp_path / "truncated.pdf", b"%PDF-1.4\n\xc2\xa1truncated")
    sheets, err = _safe_pdf_tables(bad)
    assert sheets == {}
    assert err is not None


def test_safe_pdf_text_on_truncated_pdf(tmp_path: Path) -> None:
    bad = _write_bytes(tmp_path / "truncated.pdf", b"%PDF-1.4\n\xc2\xa1truncated")
    text, err = _safe_pdf_text(bad)
    # Truncated input either returns "" silently or with an error;
    # never raises.
    assert isinstance(text, str)


@pytest.mark.parametrize(
    "missing_path",
    [
        Path("does/not/exist.pdf"),
        Path("/tmp/definitely_not_here.pdf"),
    ],
)
def test_safe_extractors_on_missing_file(missing_path: Path) -> None:
    sheets, err = _safe_pdf_tables(missing_path)
    assert sheets == {}
    assert err is not None
    text, err2 = _safe_pdf_text(missing_path)
    assert text == ""
