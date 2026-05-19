"""PDF 提取测试。用 reportlab 现造一个 PDF。"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from paperguard.extractor.pdf_text import extract_pdf_text


def _make_minimal_pdf(path: Path, text: str) -> None:
    """用 pymupdf 现造一个一页 PDF。"""
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page()  # type: ignore[no-untyped-call]
    page.insert_text((72, 100), text)  # type: ignore[no-untyped-call]
    doc.save(path)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]


def test_pdf_text_extraction(tmp_path: Path) -> None:
    p = tmp_path / "sample.pdf"
    _make_minimal_pdf(p, "Hello PaperGuard p=0.034 mean 1.23 ± 0.05")
    text = extract_pdf_text(p)
    assert "Hello PaperGuard" in text
    assert "0.034" in text


def test_pdf_text_empty(tmp_path: Path) -> None:
    """空 PDF 返回空文本而不是异常。"""
    p = tmp_path / "empty.pdf"
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page()  # type: ignore[no-untyped-call]
    doc.save(p)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    assert extract_pdf_text(p) == "\n" or extract_pdf_text(p).strip() == ""
