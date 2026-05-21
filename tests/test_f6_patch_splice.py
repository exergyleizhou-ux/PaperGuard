"""F6 patch-splice detector tests (synthetic images).

Covers:
- Skip when no opencv (mocked via PatchSpliceInput precondition)
- Skip when image too small
- Clean uniform image → no finding
- Spliced rectangular patch with different colour distribution → finding
- Privacy: every finding has ≥ 4 innocent_explanations and no verdict words
- Connected component analysis: returns largest cluster size correctly
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from paperguard.detectors.f6_patch_splice import (  # noqa: E402
    F6PatchSpliceDetector,
    PatchSpliceInput,
    _jsd,
    _largest_connected_component_size,
)


def _save_clean_image(path: Path, size: int = 256) -> Path:
    """Uniform random noise — no histogram discontinuities."""
    rng = np.random.default_rng(42)
    img = rng.integers(80, 180, (size, size, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


def _save_spliced_image(path: Path, size: int = 256) -> Path:
    """Uniform noise with a 96x96 rectangle of *very* different colour
    distribution pasted at (60, 60). The rectangle uses a tight,
    high-contrast random distribution shifted into the upper-quarter
    of the dynamic range.
    """
    rng = np.random.default_rng(42)
    img = rng.integers(80, 180, (size, size, 3), dtype=np.uint8)
    splice = rng.integers(200, 255, (96, 96, 3), dtype=np.uint8)
    img[60:156, 60:156] = splice
    cv2.imwrite(str(path), img)
    return path


def _save_tiny_image(path: Path) -> Path:
    rng = np.random.default_rng(42)
    img = rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


def test_check_applicability_no_paths() -> None:
    det = F6PatchSpliceDetector()
    ok, reason = det.check_applicability(PatchSpliceInput(image_paths=[]))
    assert ok is False
    assert "No image paths" in reason


def test_check_applicability_wrong_input() -> None:
    det = F6PatchSpliceDetector()
    ok, _ = det.check_applicability("not an input")
    assert ok is False


def test_check_applicability_ok(tmp_path: Path) -> None:
    p = _save_clean_image(tmp_path / "clean.png")
    det = F6PatchSpliceDetector()
    ok, reason = det.check_applicability(PatchSpliceInput(image_paths=[p]))
    assert ok, reason


def test_clean_image_no_finding(tmp_path: Path) -> None:
    p = _save_clean_image(tmp_path / "clean.png")
    det = F6PatchSpliceDetector()
    result = det.detect(PatchSpliceInput(image_paths=[p]))
    assert result.applicable
    assert result.findings == [] or all(
        f.severity.name == "NOTE" for f in result.findings
    )


def test_spliced_image_fires(tmp_path: Path) -> None:
    p = _save_spliced_image(tmp_path / "spliced.png")
    det = F6PatchSpliceDetector()
    result = det.detect(PatchSpliceInput(image_paths=[p]))
    assert result.applicable
    assert result.findings, "F6 should detect the spliced rectangle"
    f = result.findings[0]
    assert f.test_statistic is not None
    assert f.test_statistic >= 4.0


def test_tiny_image_skipped(tmp_path: Path) -> None:
    p = _save_tiny_image(tmp_path / "tiny.png")
    det = F6PatchSpliceDetector()
    result = det.detect(PatchSpliceInput(image_paths=[p]))
    # Image too small → _analyse_one returns None → no findings
    assert result.applicable  # opencv is installed
    assert result.findings == []


def test_innocent_explanations_count(tmp_path: Path) -> None:
    """Every finding must have ≥ 4 innocent explanations."""
    p = _save_spliced_image(tmp_path / "spliced.png")
    det = F6PatchSpliceDetector()
    result = det.detect(PatchSpliceInput(image_paths=[p]))
    for f in result.findings:
        assert len(f.innocent_explanations) >= 4


def test_no_verdict_words(tmp_path: Path) -> None:
    forbidden = ("fraud", "fabrication", "misconduct", "造假", "cheating")
    p = _save_spliced_image(tmp_path / "spliced.png")
    det = F6PatchSpliceDetector()
    result = det.detect(PatchSpliceInput(image_paths=[p]))
    for f in result.findings:
        bag = (
            f.summary + " " + f.detail + " " + " ".join(f.innocent_explanations)
        ).lower()
        for w in forbidden:
            assert w not in bag, f"forbidden word {w!r} in finding"


def test_jsd_properties() -> None:
    # Identical distributions → JSD = 0
    p = np.array([0.25, 0.25, 0.25, 0.25])
    assert _jsd(p, p) < 1e-6
    # Disjoint support → JSD near ln 2
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert 0.6 < _jsd(a, b) < 0.694


def test_largest_cc_empty() -> None:
    assert _largest_connected_component_size(np.zeros((5, 5), dtype=np.uint8)) == 0


def test_largest_cc_full() -> None:
    arr = np.ones((4, 4), dtype=np.uint8)
    assert _largest_connected_component_size(arr) == 16


def test_largest_cc_two_components() -> None:
    """Two separate 4-patch clusters → answer is 4, not 8."""
    arr = np.zeros((6, 6), dtype=np.uint8)
    # Component 1 (top-left 2x2)
    arr[0:2, 0:2] = 1
    # Component 2 (bottom-right 2x2), separated by zeros
    arr[4:6, 4:6] = 1
    assert _largest_connected_component_size(arr) == 4
