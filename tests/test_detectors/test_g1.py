"""G1 EXIF 时序测试。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import piexif  # type: ignore[import-untyped]
from PIL import Image

from paperguard.core.types import Severity
from paperguard.detectors.g1_exif_temporal import ExifInput, G1ExifTemporalDetector


def _save_jpeg_with_exif(path: Path, datetime_original: str, software: str = "") -> None:
    img = Image.new("RGB", (32, 32), (255, 0, 0))
    exif_dict: dict = {
        "0th": {},
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: datetime_original.encode("ascii"),
        },
        "GPS": {},
        "1st": {},
        "thumbnail": None,
    }
    if software:
        exif_dict["0th"][piexif.ImageIFD.Software] = software.encode("ascii")
    exif_bytes = piexif.dump(exif_dict)
    img.save(path, "jpeg", exif=exif_bytes)


def test_g1_flags_capture_before_experiment(tmp_path: Path) -> None:
    p = tmp_path / "early.jpg"
    _save_jpeg_with_exif(p, "2018:01:15 10:00:00")
    inp = ExifInput(
        image_paths=[p],
        claimed_experiment_start=datetime(2020, 1, 1),
    )
    result = G1ExifTemporalDetector().detect(inp, seed=42)
    assert result.applicable
    critical = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(critical) >= 1


def test_g1_flags_capture_after_submission(tmp_path: Path) -> None:
    p = tmp_path / "late.jpg"
    _save_jpeg_with_exif(p, "2025:06:01 10:00:00")
    inp = ExifInput(
        image_paths=[p],
        paper_submission_date=datetime(2023, 1, 1),
    )
    result = G1ExifTemporalDetector().detect(inp, seed=42)
    assert result.applicable
    critical = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(critical) >= 1


def test_g1_flags_photoshop_software(tmp_path: Path) -> None:
    p = tmp_path / "edited.jpg"
    _save_jpeg_with_exif(
        p, "2024:01:01 10:00:00", software="Adobe Photoshop 2024"
    )
    inp = ExifInput(image_paths=[p])
    result = G1ExifTemporalDetector().detect(inp, seed=42)
    concerns = [
        f for f in result.findings if "photoshop" in f.detail.lower()
    ]
    assert len(concerns) >= 1


def test_g1_inapplicable_no_images() -> None:
    inp = ExifInput(image_paths=[])
    result = G1ExifTemporalDetector().detect(inp, seed=42)
    assert not result.applicable
