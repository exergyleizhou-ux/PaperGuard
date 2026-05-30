"""Offline tests for the figure/table detector wiring (P2 connector).

These never touch the network. They exercise the orchestration contract:
missing source, non-PDF (C1 skipped), no images extracted, and — when Pillow
is available — two real PNGs flowing into the image-forensics detectors.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from paperguard.evidence.figure_pipeline import (
    FigurePipelineResult,
    run_figure_pipeline,
)


def test_missing_source_reports_note(tmp_path: Path) -> None:
    res = run_figure_pipeline(tmp_path / "does_not_exist.pdf")
    assert isinstance(res, FigurePipelineResult)
    assert res.results == []
    assert res.image_paths == []
    assert any("not found" in n for n in res.notes)


def test_non_pdf_text_file_skips_cleanly(tmp_path: Path) -> None:
    """A .txt has no images and is not a PDF -> no detectors, honest notes."""
    f = tmp_path / "manuscript.txt"
    f.write_text("hello world", encoding="utf-8")
    res = run_figure_pipeline(f, work_dir=tmp_path / "work")
    assert res.results == []
    assert res.n_baseline_tables == 0
    assert any("no figure images" in n for n in res.notes)


def test_docx_with_no_media_skips_c1(tmp_path: Path) -> None:
    """A .docx is not a PDF, so C1 (baseline) must not run."""
    f = tmp_path / "doc.docx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", "<x/>")
    res = run_figure_pipeline(f, work_dir=tmp_path / "work")
    # no images -> no image detectors; non-pdf -> C1 not attempted
    assert res.n_baseline_tables == 0
    assert all(r.detector_id != "C1" for r in res.results)


def _make_noise_png(path: Path, seed: int, size: int = 256) -> bool:
    """Write a >=8KB noise PNG so the docx extractor won't filter it as an icon.

    Uses seeded high-entropy random pixels: a structured pattern compresses
    far below the 8KB threshold, but random RGB does not.
    """
    try:
        from PIL import Image
    except ImportError:
        return False
    import random

    rng = random.Random(seed)
    img = Image.new("RGB", (size, size))
    img.putdata(
        [
            (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(size * size)
        ]
    )
    img.save(path)
    return path.stat().st_size >= 8000


def test_two_images_run_image_detectors(tmp_path: Path) -> None:
    """Two extractable images -> image-forensics detectors all return a result.

    We feed a .docx whose media are two real >=8KB PNGs, so the docx image
    extractor yields exactly two paths into the pipeline.
    """
    img_dir = tmp_path / "src_imgs"
    img_dir.mkdir()
    p1 = img_dir / "a.png"
    p2 = img_dir / "b.png"
    if not (_make_noise_png(p1, 1) and _make_noise_png(p2, 99)):
        pytest.skip("Pillow not installed or PNGs below 8KB threshold")

    f = tmp_path / "withmedia.docx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", "<x/>")
        z.write(p1, "word/media/image1.png")
        z.write(p2, "word/media/image2.png")

    res = run_figure_pipeline(f, work_dir=tmp_path / "work")
    assert len(res.image_paths) == 2
    # All six image detectors produced a result object (applicable or skipped).
    ids = {r.detector_id for r in res.results}
    assert {"F1", "F2", "F3", "F5", "F6", "F7"}.issubset(ids)


def test_no_verdict_language_in_notes(tmp_path: Path) -> None:
    """The wiring layer must never inject verdict language (IRON RULE)."""
    res = run_figure_pipeline(tmp_path / "missing.pdf")
    blob = " ".join(res.notes).lower()
    for banned in ("fraud", "guilty", "fabricated", "misconduct"):
        assert banned not in blob
