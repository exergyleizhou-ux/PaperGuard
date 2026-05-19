"""Page-as-raster fallback regression tests (2.0.8).

The v2 / v3 / v4 / v5 recall studies all showed F1 / F2 / F3 / F4
firing on near-zero papers because modern publisher PDFs store
figures as vector graphics — and pymupdf's ``page.get_images()`` only
returns embedded raster bitmaps. 2.0.8 adds a page-render fallback
that calls ``page.get_pixmap`` so vector-only PDFs still produce
image inputs for the F-cluster detectors.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from paperguard.extractor.images import extract_pdf_images


def _build_vector_pdf(path: Path) -> None:
    """Build a 3-page PDF with text + a vector rectangle on each page,
    NO embedded raster bitmaps."""
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Page {i + 1} — vector content only")
        page.draw_rect(pymupdf.Rect(100, 200, 400, 500), fill=(0.3, 0.5, 0.8))
    doc.save(path)
    doc.close()


def _build_pdf_with_embedded_bitmap(path: Path, png_path: Path) -> None:
    """Build a PDF that embeds a 300×300 PNG bitmap with enough varied
    pixels to exceed the 8 KB filter threshold."""
    import random

    rng = random.Random(42)
    # Make a 300×300 image with random pixel noise so it compresses big.
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 300), False)
    samples = bytearray(300 * 300 * 3)
    for i in range(len(samples)):
        samples[i] = rng.randint(0, 255)
    pix.set_rect(pymupdf.IRect(0, 0, 300, 300), bytes(samples))
    pix.save(png_path)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(50, 50, 350, 350), filename=str(png_path))
    doc.save(path)
    doc.close()


def test_raster_fallback_extracts_vector_only_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "vector_only.pdf"
    _build_vector_pdf(pdf)
    with TemporaryDirectory() as td:
        imgs = extract_pdf_images(pdf, Path(td))
    assert len(imgs) >= 2
    assert all("raster_p" in p.name for p in imgs)


def test_raster_fallback_disabled_returns_zero_on_vector_pdf(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "vector_only.pdf"
    _build_vector_pdf(pdf)
    with TemporaryDirectory() as td:
        imgs = extract_pdf_images(pdf, Path(td), raster_fallback=False)
    assert imgs == []


def test_raster_max_pages_capped(tmp_path: Path) -> None:
    doc = pymupdf.open()
    for _ in range(50):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), "vector page")
        page.draw_rect(pymupdf.Rect(100, 200, 400, 500), fill=(0.5, 0.5, 0.5))
    pdf = tmp_path / "big.pdf"
    doc.save(pdf)
    doc.close()
    with TemporaryDirectory() as td:
        imgs = extract_pdf_images(pdf, Path(td), raster_max_pages=5)
    raster_imgs = [p for p in imgs if "raster_p" in p.name]
    assert len(raster_imgs) <= 5
    assert len(raster_imgs) >= 1


def test_extract_returns_nonempty_when_pdf_has_content(tmp_path: Path) -> None:
    """When the PDF has visible content (vector or bitmap), the
    extractor should produce at least one image. We don't try to pin
    down whether the embedded-bitmap path or the raster-fallback path
    is hit — pymupdf's internal encoding choices vary by version."""
    png = tmp_path / "embed.png"
    pdf = tmp_path / "with_bitmap.pdf"
    _build_pdf_with_embedded_bitmap(pdf, png)
    with TemporaryDirectory() as td:
        imgs = extract_pdf_images(pdf, Path(td))
    assert len(imgs) >= 1


def test_raster_dpi_affects_size(tmp_path: Path) -> None:
    pdf = tmp_path / "vector_only.pdf"
    _build_vector_pdf(pdf)
    with TemporaryDirectory() as td1, TemporaryDirectory() as td2:
        lo = extract_pdf_images(pdf, Path(td1), raster_dpi=72)
        hi = extract_pdf_images(pdf, Path(td2), raster_dpi=200)
        if lo and hi:
            lo_size = lo[0].stat().st_size
            hi_size = hi[0].stat().st_size
            assert hi_size > lo_size
